"""In-memory scoring engine backing the API.

Builds the population, runs the replay backtest, scores the held-out fold and
records every resulting decision in the audit ledger. Everything the dashboard
shows is read from this one object, so the numbers on screen and the numbers in
`artifacts/evaluation/report.json` cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..agent.actions import ACTION_SPEC, Action, Decision, band_for, decide
from ..agent.evidence import EvidencePacket, build_evidence
from ..agent.narrate import Narration, narrate
from ..config import ARTIFACTS_DIR, SimulationConfig
from ..evaluation.replay import ReplayResult, run_replay
from ..ledger.ledger import DecisionLedger
from ..simulator.generate import generate

LEDGER_PATH = ARTIFACTS_DIR / "ledger" / "decisions.ndjson"


@dataclass
class Engine:
    replay: ReplayResult
    ledger: DecisionLedger
    review_threshold: float
    action_threshold: float
    baseline: pd.Series
    decisions: dict[str, Decision] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    truth: dict[str, bool] = field(default_factory=dict)
    _narration_cache: dict[str, Narration] = field(default_factory=dict)

    # ---------------------------------------------------------------- build
    @classmethod
    def build(
        cls,
        seed: int = SimulationConfig.seed,
        train_cutoff_day: int = 55,
        score_day: int = 120,
        reset_ledger: bool = True,
    ) -> Engine:
        dataset = generate(SimulationConfig(seed=seed))
        replay = run_replay(dataset, train_cutoff_day, score_day, verbose=False)

        optimal = replay.report["model"]["cost_optimal_threshold"]
        review_threshold = max(0.05, optimal * 0.4)
        action_threshold = min(0.95, optimal * 1.15)

        if reset_ledger and LEDGER_PATH.exists():
            LEDGER_PATH.unlink()
        ledger = DecisionLedger(path=LEDGER_PATH)
        ledger.append(
            "run_started",
            {
                "seed": seed,
                "train_cutoff_day": train_cutoff_day,
                "score_day": score_day,
                "review_threshold": round(review_threshold, 4),
                "action_threshold": round(action_threshold, 4),
                "model_average_precision": replay.report["model"]["average_precision"],
            },
        )

        features = replay.test_features
        feature_cols = [c for c in features.columns if c != "account_id"]
        low_risk = features[replay.model_scores < 0.10]
        baseline = (low_risk if len(low_risk) > 50 else features)[feature_cols].median()

        engine = cls(
            replay=replay,
            ledger=ledger,
            review_threshold=review_threshold,
            action_threshold=action_threshold,
            baseline=baseline,
        )

        truth_map = dataset.accounts.set_index("account_id")["label_is_ring"].to_dict()
        for account_id, score in zip(
            features["account_id"], replay.model_scores, strict=True
        ):
            engine.scores[account_id] = float(score)
            engine.truth[account_id] = bool(truth_map.get(account_id, False))

        engine._decide_all()
        return engine

    def _decide_all(self) -> None:
        """Score, assemble evidence and decide for everything above the review band."""
        for account_id, score in self.scores.items():
            band = band_for(score, self.review_threshold, self.action_threshold)
            if band == "allow":
                continue
            packet = self.evidence_for(account_id, score, band)
            exposure = float(packet.facts["claimed_inr"])
            decision = decide(
                account_id, score, band, packet.sufficiency,
                packet.sufficiency_reason, exposure,
                claims_filed=int(packet.facts["claims"]),
            )
            self.decisions[account_id] = decision
            self.ledger.append(
                "decision",
                {
                    **decision.to_dict(),
                    "sufficiency": packet.sufficiency,
                    "evidence_links": len(packet.links),
                    "community_size": packet.community_size,
                },
                account_id,
            )

    # ------------------------------------------------------------- queries
    def evidence_for(
        self, account_id: str, score: float | None = None, band: str | None = None
    ) -> EvidencePacket:
        score = self.scores[account_id] if score is None else score
        band = band or band_for(score, self.review_threshold, self.action_threshold)
        return build_evidence(
            account_id, score, band, self.replay.test_features,
            self.replay.identity, self.replay.communities, self.baseline,
        )

    def narration_for(self, account_id: str, allow_llm: bool = True) -> Narration:
        if account_id not in self._narration_cache:
            self._narration_cache[account_id] = narrate(
                self.evidence_for(account_id), allow_llm=allow_llm
            )
        return self._narration_cache[account_id]

    def alerts(self, band: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        rows = []
        for account_id, decision in self.decisions.items():
            if band and decision.band != band:
                continue
            packet_facts = self.replay.test_features.loc[
                self.replay.test_features["account_id"] == account_id
            ].iloc[0]
            rows.append(
                {
                    **decision.to_dict(),
                    "community_size": int(packet_facts.get("community_size", 1)),
                    "linked_accounts": int(packet_facts.get("graph_degree", 0)),
                    "claims": int(packet_facts.get("n_claims", 0)),
                    "claimed_inr": round(float(packet_facts.get("claimed_amount", 0.0)), 2),
                    "orders": int(packet_facts.get("n_orders", 0)),
                    "effect": ACTION_SPEC[decision.action]["effect"],
                    # Held-out ground truth, shown in the demo so a reviewer can
                    # judge the system's calls. Never used to make them.
                    "ground_truth_is_ring": self.truth.get(account_id),
                }
            )
        rows.sort(key=lambda r: -r["score"])
        return rows[:limit]

    def subgraph(self, account_id: str, max_nodes: int = 40) -> dict[str, Any]:
        """Nodes and edges for the evidence visualisation."""
        graph = self.replay.identity.graph
        if account_id not in graph:
            return {"nodes": [{"id": account_id, "score": self.scores.get(account_id, 0.0),
                               "focus": True, "degree": 0}], "edges": []}

        community = self.replay.communities
        cid = community.community_of(account_id)
        members = set(community.members.get(cid, [account_id]))
        members.update(dict(graph[account_id]).keys())
        members = set(list(members)[:max_nodes])
        members.add(account_id)

        nodes = [
            {
                "id": member,
                "score": round(self.scores.get(member, 0.0), 4),
                "focus": member == account_id,
                "degree": int(graph.degree(member)) if member in graph else 0,
                "ground_truth_is_ring": self.truth.get(member),
            }
            for member in sorted(members)
        ]
        edges = []
        for a in members:
            if a not in graph:
                continue
            for b in graph[a]:
                if b in members and a < b:
                    evidence = self.replay.identity.edge_evidence(a, b)
                    types = sorted({t for t, _v, _c in evidence})
                    edges.append(
                        {
                            "source": a,
                            "target": b,
                            "weight": round(graph[a][b]["weight"], 4),
                            "identifier_types": types,
                        }
                    )
        return {"nodes": nodes, "edges": edges}

    def record_review(self, account_id: str, verdict: str, note: str, reviewer: str) -> dict:
        """Human override. The ledger keeps both the machine call and the human one."""
        prior = self.decisions.get(account_id)
        entry = self.ledger.append(
            "human_review",
            {
                "verdict": verdict,
                "note": note,
                "reviewer": reviewer,
                "overrides_action": prior.action.value if prior else None,
                "model_score": self.scores.get(account_id),
            },
            account_id,
        )
        return {"entry_id": entry.entry_id, "index": entry.index, "chain_head": self.ledger.head()}

    def overview(self) -> dict[str, Any]:
        report = self.replay.report
        ok, detail = self.ledger.verify()
        bands: dict[str, int] = {}
        for decision in self.decisions.values():
            bands[decision.action.value] = bands.get(decision.action.value, 0) + 1
        # Precision on the only thing a customer actually experiences. The raw
        # model precision counts every flag; this counts only the accounts that
        # were restricted, which is the number that matters to a real merchant.
        visible = [
            d for d in self.decisions.values()
            if d.action in (Action.STEP_UP_VERIFICATION, Action.HOLD_REFUND)
        ]
        wrongly_restricted = sum(1 for d in visible if not self.truth.get(d.account_id, False))

        return {
            "split": report["split"],
            "customer_visible": {
                "total_actions": len(visible),
                "on_legitimate_accounts": wrongly_restricted,
                "precision": round(
                    (len(visible) - wrongly_restricted) / max(1, len(visible)), 4
                ),
                "raw_model_false_positives": report["model"]["at_cost_optimal"]["fp"],
            },
            "model": {
                k: report["model"][k]
                for k in (
                    "average_precision", "roc_auc", "cost_optimal_threshold",
                    "net_benefit_inr", "exposure_recall", "abuse_exposure_inr",
                    "exposure_caught_inr", "legit_value_disrupted_inr",
                )
            },
            "at_operating_point": report["model"]["at_cost_optimal"],
            "rules_baseline": report["rules_baseline"],
            "banded_policy": report["banded_policy"],
            "thresholds": {
                "review": round(self.review_threshold, 4),
                "action": round(self.action_threshold, 4),
            },
            "action_counts": bands,
            "ledger": {"entries": len(self.ledger.entries), "verified": ok, "detail": detail,
                       "head": self.ledger.head()},
        }

"""Robustness studies that a single backtest run cannot answer.

Four questions a risk panel will ask, and which the headline number does not
address:

1. **Is 0.978 real, or is it one lucky seed?**            -> `seed_variance`
2. **Is the graph earning its keep, or would ordinary
   behavioural features get you there?**                  -> `ablation`
3. **You evaluated at 5.3% prevalence. What happens at
   1%, which is closer to reality?**                      -> `prevalence_sensitivity`
4. **Your false positives are households and hostel
   residents. How unequal is that, exactly?**             -> `fairness_by_cohort`
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..agent.actions import Action, band_for, decide
from ..agent.evidence import build_evidence
from ..config import SimulationConfig
from ..graph.features import FEATURE_FAMILIES, family_columns
from ..simulator.generate import generate
from . import metrics as met
from .replay import ReplayResult, run_replay

CUSTOMER_VISIBLE = (Action.STEP_UP_VERIFICATION, Action.HOLD_REFUND)


# --------------------------------------------------------------------------
# 1. Seed variance
# --------------------------------------------------------------------------

def seed_variance(
    seeds: list[int],
    train_cutoff_day: int = 55,
    score_day: int = 120,
    verbose: bool = True,
) -> dict[str, Any]:
    """Re-run the whole pipeline on independently generated populations.

    Every headline in this repository comes from one seed. That is the single
    easiest attack on a synthetic benchmark, so we answer it directly: generate
    N populations, run the full replay on each, and report the spread.
    """
    rows = []
    for seed in seeds:
        dataset = generate(SimulationConfig(seed=seed))
        result = run_replay(
            dataset, train_cutoff_day, score_day, verbose=False, skip_importance=True
        )
        report = result.report
        levels = {d["evasion_level"]: d["recall"] for d in report["recall_by_evasion_level"]}
        rules_levels = {
            d["evasion_level"]: d["recall"] for d in report["rules_recall_by_evasion_level"]
        }
        rows.append(
            {
                "seed": seed,
                "n_test": report["split"]["n_test"],
                "prevalence": report["split"]["test_prevalence"],
                "model_ap": report["model"]["average_precision"],
                "rules_ap": report["rules_baseline"]["average_precision"],
                "precision": report["model"]["at_cost_optimal"]["precision"],
                "recall": report["model"]["at_cost_optimal"]["recall"],
                "f1": report["model"]["at_cost_optimal"]["f1"],
                "false_positives": report["model"]["at_cost_optimal"]["fp"],
                "net_benefit_inr": report["model"]["net_benefit_inr"],
                "recall_L0_L6": float(np.mean([levels.get(i, np.nan) for i in range(7)])),
                "recall_L7_L9": float(np.mean([levels.get(i, np.nan) for i in range(7, 10)])),
                "rules_recall_L7_L9": float(
                    np.mean([rules_levels.get(i, np.nan) for i in range(7, 10)])
                ),
            }
        )
        if verbose:
            r = rows[-1]
            print(
                f"  seed {seed}: AP={r['model_ap']:.4f} P={r['precision']:.3f} "
                f"R={r['recall']:.3f} L7-9={r['recall_L7_L9']:.3f}"
            )

    df = pd.DataFrame(rows)
    numeric = df.drop(columns=["seed"])
    summary = {
        col: {
            "mean": round(float(numeric[col].mean()), 4),
            "std": round(float(numeric[col].std(ddof=1)), 4),
            "min": round(float(numeric[col].min()), 4),
            "max": round(float(numeric[col].max()), 4),
        }
        for col in numeric.columns
    }
    return {"seeds": seeds, "per_seed": df.to_dict("records"), "summary": summary}


# --------------------------------------------------------------------------
# 2. Feature-family ablation
# --------------------------------------------------------------------------

#: Each entry trains a fresh model on only these families.
ABLATION_SETS: dict[str, list[str]] = {
    "all": list(FEATURE_FAMILIES),
    "behavioural_only": ["behavioural"],
    "behavioural+churn": ["behavioural", "identity_churn"],
    "behavioural+temporal": ["behavioural", "temporal"],
    "no_graph": ["behavioural", "identity_churn", "temporal"],
    "graph_only": ["graph", "neighbour", "community"],
    "no_neighbour": ["behavioural", "identity_churn", "temporal", "graph", "community"],
}


def ablation(
    seed: int = SimulationConfig.seed,
    train_cutoff_day: int = 55,
    score_day: int = 120,
    verbose: bool = True,
) -> dict[str, Any]:
    """Train the same model on subsets of the feature families.

    The interesting comparison is `no_graph` versus `all`: if per-account
    behaviour alone reaches the same place, the entire graph layer is
    decoration and should be deleted.
    """
    dataset = generate(SimulationConfig(seed=seed))
    rows = []
    for name, families in ABLATION_SETS.items():
        cols = family_columns(families)
        result = run_replay(
            dataset, train_cutoff_day, score_day, verbose=False,
            skip_importance=True, columns=cols,
        )
        report = result.report
        levels = {d["evasion_level"]: d["recall"] for d in report["recall_by_evasion_level"]}
        rows.append(
            {
                "feature_set": name,
                "families": ",".join(families),
                "n_features": len(cols),
                "average_precision": report["model"]["average_precision"],
                "precision": report["model"]["at_cost_optimal"]["precision"],
                "recall": report["model"]["at_cost_optimal"]["recall"],
                "recall_L0_L6": round(
                    float(np.mean([levels.get(i, np.nan) for i in range(7)])), 4
                ),
                "recall_L7_L9": round(
                    float(np.mean([levels.get(i, np.nan) for i in range(7, 10)])), 4
                ),
                "net_benefit_inr": report["model"]["net_benefit_inr"],
            }
        )
        if verbose:
            r = rows[-1]
            print(
                f"  {name:22} ({r['n_features']:2d} feats) AP={r['average_precision']:.4f} "
                f"L0-6={r['recall_L0_L6']:.3f} L7-9={r['recall_L7_L9']:.3f}"
            )
    return {"seed": seed, "results": rows}


# --------------------------------------------------------------------------
# 3. Prevalence sensitivity
# --------------------------------------------------------------------------

def prevalence_sensitivity(
    result: ReplayResult,
    targets: tuple[float, ...] = (0.01, 0.02, 0.03, 0.04, 0.0528),
    n_bootstrap: int = 300,
    rng_seed: int = 7,
) -> dict[str, Any]:
    """How precision moves if organised abuse is rarer than we assumed.

    Rather than regenerate populations at each rate — which confounds the
    prevalence effect with retraining noise — we hold the trained model and the
    threshold fixed and resample the held-out fold to the target prevalence.

    Recall is unaffected by subsampling positives, which is the point: at lower
    prevalence you catch the same fraction of abusers and pay for it with a
    worse precision, because the negatives are unchanged and the positives are
    fewer.
    """
    rng = np.random.default_rng(rng_seed)
    y = result.y_true.astype(bool)
    scores = result.model_scores
    threshold = result.report["model"]["cost_optimal_threshold"]

    pos_idx = np.flatnonzero(y)
    neg_idx = np.flatnonzero(~y)
    n_neg = len(neg_idx)

    rows = []
    for target in targets:
        k = int(round(target * n_neg / (1 - target)))
        feasible = min(k, len(pos_idx))
        precisions, recalls = [], []
        for _ in range(n_bootstrap):
            sampled = rng.choice(pos_idx, size=feasible, replace=False)
            idx = np.concatenate([sampled, neg_idx])
            cm = met.confusion_at(y[idx], scores[idx], threshold)
            precisions.append(cm.precision)
            recalls.append(cm.recall)
        rows.append(
            {
                "target_prevalence": target,
                "positives_used": feasible,
                "achieved_prevalence": round(feasible / (feasible + n_neg), 4),
                "precision_mean": round(float(np.mean(precisions)), 4),
                "precision_p2_5": round(float(np.percentile(precisions, 2.5)), 4),
                "precision_p97_5": round(float(np.percentile(precisions, 97.5)), 4),
                "recall_mean": round(float(np.mean(recalls)), 4),
                "truncated": feasible < k,
            }
        )
    return {"threshold": threshold, "n_negatives": int(n_neg), "results": rows}


# --------------------------------------------------------------------------
# 4. Fairness
# --------------------------------------------------------------------------

def _decisions(result: ReplayResult, review_t: float, action_t: float) -> dict[str, Any]:
    features = result.test_features
    feature_cols = [c for c in features.columns if c != "account_id"]
    low = features[result.model_scores < 0.10]
    baseline = (low if len(low) > 50 else features)[feature_cols].median()

    out = {}
    for account_id, score in zip(features["account_id"], result.model_scores, strict=True):
        band = band_for(float(score), review_t, action_t)
        if band == "allow":
            out[account_id] = Action.ALLOW
            continue
        packet = build_evidence(
            account_id, float(score), band, features,
            result.identity, result.communities, baseline,
        )
        decision = decide(
            account_id, float(score), band, packet.sufficiency,
            packet.sufficiency_reason, float(packet.facts["claimed_inr"]),
            claims_filed=int(packet.facts["claims"]),
        )
        out[account_id] = decision.action
    return out


def fairness_by_cohort(
    result: ReplayResult, dataset, review_t: float | None = None, action_t: float | None = None
) -> dict[str, Any]:
    """Disparate impact of customer-visible actions across legitimate cohorts.

    The question is not "how accurate is the model" but: **among people who did
    nothing wrong, who gets restricted?** If a hostel resident is many times
    more likely to be restricted than a solo shopper, that is a harm the
    accuracy numbers hide completely.

    Restricted here means a customer-visible action - step-up verification or a
    held refund. Monitoring and review-queue entries are invisible to the
    customer and are reported separately.
    """
    optimal = result.report["model"]["cost_optimal_threshold"]
    review_t = review_t if review_t is not None else max(0.05, optimal * 0.4)
    action_t = action_t if action_t is not None else min(0.95, optimal * 1.15)

    actions = _decisions(result, review_t, action_t)
    cohort = dataset.accounts.set_index("account_id")["cohort"].to_dict()
    truth = dataset.accounts.set_index("account_id")["label_is_ring"].to_dict()

    rows = []
    for name in ("solo", "household", "hub"):
        members = [
            a for a in actions
            if cohort.get(a) == name and not truth.get(a, False)
        ]
        if not members:
            continue
        restricted = sum(1 for a in members if actions[a] in CUSTOMER_VISIBLE)
        reviewed = sum(1 for a in members if actions[a] == Action.QUEUE_FOR_REVIEW)
        monitored = sum(1 for a in members if actions[a] == Action.MONITOR)
        rows.append(
            {
                "cohort": name,
                "legitimate_accounts": len(members),
                "restricted": restricted,
                "restriction_rate": round(restricted / len(members), 5),
                "queued_for_review": reviewed,
                "review_rate": round(reviewed / len(members), 5),
                "monitored": monitored,
                "any_flag_rate": round(
                    (restricted + reviewed + monitored) / len(members), 5
                ),
            }
        )

    df = pd.DataFrame(rows)
    reference = df.loc[df["cohort"] == "solo", "restriction_rate"]
    ref = float(reference.iloc[0]) if len(reference) else 0.0
    total_restricted = int(df["restricted"].sum())
    total_flagged = int((df["restricted"] + df["queued_for_review"]).sum())

    for row in rows:
        # Disparate impact ratio against the solo-shopper reference group.
        # A ratio of 1.0 is parity; the US "four-fifths rule" treats <0.8 or
        # >1.25 as evidence of adverse impact.
        #
        # When the reference rate is exactly zero the ratio is undefined - and
        # that is a *stronger* finding than any finite ratio, not a missing
        # value. We therefore also report each cohort's share of all harm,
        # which stays meaningful however small the reference group's rate is.
        row["disparate_impact_vs_solo"] = (
            round(row["restriction_rate"] / ref, 2) if ref > 0 else None
        )
        row["share_of_all_restrictions"] = (
            round(row["restricted"] / total_restricted, 4) if total_restricted else 0.0
        )
        row["share_of_all_flags"] = (
            round((row["restricted"] + row["queued_for_review"]) / total_flagged, 4)
            if total_flagged else 0.0
        )

    undefined = ref == 0.0 and total_restricted > 0
    household_share = float(
        df.loc[df["cohort"] == "household", "legitimate_accounts"].sum()
        / max(1, df["legitimate_accounts"].sum())
    )
    if undefined:
        finding = (
            "No solo shopper is ever restricted, so the disparate-impact ratio is "
            "undefined rather than merely large. Every wrongly restricted customer "
            "lives in a multi-account household, and households are "
            f"{household_share:.0%} of the legitimate population."
        )
    else:
        finding = "Restriction rates are non-zero in the reference group; see the ratios."

    return {
        "thresholds": {"review": round(review_t, 4), "action": round(action_t, 4)},
        "definition": (
            "restriction_rate = P(customer-visible action | account is legitimate). "
            "Monitoring and review-queue entries are not customer-visible."
        ),
        "by_cohort": rows,
        "reference_group": "solo",
        "disparate_impact_undefined": undefined,
        "finding": finding,
    }

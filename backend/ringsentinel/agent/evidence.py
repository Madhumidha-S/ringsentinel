"""Evidence packets: why an account was flagged, in citable form.

An alert nobody can audit is a liability. Every packet this module produces is
grounded in three things a reviewer can independently check:

* the **peers** the account is bound to, and the identifier type that binds
  each one (values are redacted - a reviewer needs to know that two accounts
  share a card, not what the card is);
* the **behavioural facts** on the account's own record;
* the **contributing factors**, i.e. which features sit furthest from the
  legitimate-population baseline, in the risky direction.

The packet also carries a `sufficiency` verdict. Thin evidence is not escalated
into a confident story - it is routed to a human. Refusing to explain is a
feature.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from ..graph.build import IdentityGraph
from ..graph.communities import Communities

# Features whose *high* values indicate risk, with a plain-language rendering.
RISK_FEATURES: dict[str, str] = {
    "component_size": "belongs to a cluster of {value:.0f} linked accounts",
    "graph_weighted_degree": "carries identity links to other accounts totalling {value:.2f} "
                             "in evidence weight",
    "n_strong_links": "shares a strong identifier (inbox, phone, device or card) {value:.0f} times",
    "max_edge_weight": "has a single strongest link to another account scoring {value:.2f}",
    "claim_rate": "files a refund claim on {value:.0%} of its orders",
    "neighbour_claim_rate": "sits beside accounts that claim on {value:.0%} of their orders",
    "neighbour_max_claim_rate": "has a linked peer claiming on {value:.0%} of its orders",
    "community_claim_rate": "sits in a cluster claiming on {value:.0%} of orders",
    "devices_per_order": "uses {value:.2f} distinct devices per order",
    "cards_per_order": "uses {value:.2f} distinct cards per order",
    "signup_burst_24h": "signed up within 24 hours of {value:.0f} linked accounts",
    "inr_claim_share": "files item-not-received on {value:.0%} of its claims",
    "promo_rate": "redeems a promotion on {value:.0%} of orders",
    "claimed_value_share": "has claimed back {value:.0%} of what it spent",
}

IDENTIFIER_LABELS = {
    "email_norm": "same email inbox (after normalisation)",
    "phone": "same phone number",
    "device_id": "same device fingerprint",
    "card_token": "same payment instrument",
    "ship_address_norm": "same shipping address",
    "ip": "same network address",
}


def redact(value: str) -> str:
    """Stable, non-reversible reference to an identifier value."""
    return hashlib.sha256(value.encode()).hexdigest()[:10]


@dataclass
class LinkEvidence:
    peer_account_id: str
    identifier_type: str
    identifier_ref: str
    description: str
    weight: float


@dataclass
class EvidencePacket:
    account_id: str
    score: float
    band: str
    community_id: int | None
    community_size: int
    peers: list[str]
    links: list[LinkEvidence]
    facts: dict[str, Any]
    contributing_factors: list[dict[str, Any]]
    sufficiency: str
    sufficiency_reason: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["links"] = [asdict(link) if not isinstance(link, dict) else link for link in self.links]
        return d

    def citable_ids(self) -> set[str]:
        """Every identifier a narration is permitted to reference."""
        ids = {self.account_id, *self.peers}
        ids.update(link.identifier_ref for link in self.links)
        return ids


def build_evidence(
    account_id: str,
    score: float,
    band: str,
    features: pd.DataFrame,
    identity: IdentityGraph,
    communities: Communities,
    baseline: pd.Series,
    max_peers: int = 12,
    max_links: int = 20,
) -> EvidencePacket:
    """Assemble the audit packet for one account.

    `baseline` is the median feature vector of the low-risk population, used as
    the comparison point for contributing factors.
    """
    row = features.loc[features["account_id"] == account_id]
    if row.empty:
        raise KeyError(f"account {account_id} not present in feature frame")
    row = row.iloc[0]

    cid = communities.community_of(account_id)
    members = [m for m in communities.members.get(cid, []) if m != account_id] if cid else []

    links: list[LinkEvidence] = []
    for peer, _weight in identity.neighbours(account_id)[:max_peers]:
        for id_type, value, contribution in identity.edge_evidence(account_id, peer):
            links.append(
                LinkEvidence(
                    peer_account_id=peer,
                    identifier_type=id_type,
                    identifier_ref=redact(value),
                    description=IDENTIFIER_LABELS.get(id_type, id_type),
                    weight=round(float(contribution), 4),
                )
            )
    links.sort(key=lambda link: -link.weight)
    links = links[:max_links]

    factors = []
    for feat, template in RISK_FEATURES.items():
        if feat not in row.index:
            continue
        value = float(row[feat])
        base = float(baseline.get(feat, 0.0))
        if value <= base:
            continue
        lift = value / base if base > 0 else float("inf")
        factors.append(
            {
                "feature": feat,
                "value": round(value, 4),
                "population_median": round(base, 4),
                "lift": round(lift, 2) if lift != float("inf") else None,
                "statement": template.format(value=value),
            }
        )
    factors.sort(key=lambda f: -(f["lift"] or 999))
    factors = factors[:6]

    facts = {
        "orders": int(row.get("n_orders", 0)),
        "claims": int(row.get("n_claims", 0)),
        "claim_rate": round(float(row.get("claim_rate", 0.0)), 4),
        "total_spend_inr": round(float(row.get("total_amount", 0.0)), 2),
        "claimed_inr": round(float(row.get("claimed_amount", 0.0)), 2),
        "granted_refunds_inr": round(float(row.get("granted_amount", 0.0)), 2),
        "account_age_days": round(float(row.get("account_age_days", 0.0)), 1),
        "distinct_devices": int(row.get("n_devices", 0)),
        "distinct_cards": int(row.get("n_cards", 0)),
        "linked_accounts": int(row.get("graph_degree", 0)),
    }

    sufficiency, reason = _assess_sufficiency(row, links, factors)

    return EvidencePacket(
        account_id=account_id,
        score=round(float(score), 4),
        band=band,
        community_id=cid,
        community_size=len(members) + 1,
        peers=members[:max_peers],
        links=links,
        facts=facts,
        contributing_factors=factors,
        sufficiency=sufficiency,
        sufficiency_reason=reason,
    )


def _assess_sufficiency(
    row: pd.Series, links: list[LinkEvidence], factors: list[dict[str, Any]]
) -> tuple[str, str]:
    """Decide whether the evidence can carry an automated decision.

    A high score built on nothing but weak network-level links is exactly the
    case that produces confident, wrong, unexplainable restrictions. We would
    rather hand it to a person.
    """
    strong_links = [
        link for link in links
        if link.identifier_type in ("email_norm", "phone", "device_id", "card_token")
    ]
    n_orders = float(row.get("n_orders", 0))

    if n_orders < 2:
        return "insufficient", (
            "fewer than two orders on record; behavioural features are not yet meaningful"
        )
    if not links:
        return "insufficient", (
            "no identity links to any other account; a ring finding cannot rest on "
            "single-account behaviour alone"
        )
    if not strong_links:
        return "weak", (
            f"{len(links)} link(s) present but none via a strong identifier - "
            "shared address or network alone is consistent with a household, "
            "hostel or office"
        )
    if len(strong_links) >= 2 and len(factors) >= 3:
        return "strong", (
            f"{len(strong_links)} strong-identifier link(s) plus {len(factors)} "
            "behavioural factors above the population baseline"
        )
    return "moderate", (
        f"{len(strong_links)} strong-identifier link(s) with limited corroborating behaviour"
    )

"""Transparent rule baseline.

This is the system a competent engineer writes in an afternoon without any
machine learning, and it is the bar the model has to clear to justify its
existence. We report it alongside every model result.

It is deliberately a *good* baseline, not a strawman: it uses the same graph
the model uses, and its thresholds are tuned on the training split.
"""

from __future__ import annotations

import pandas as pd


def rule_scores(features: pd.DataFrame) -> pd.Series:
    """Hand-written risk score in [0, 1]. Higher is riskier."""
    f = features
    score = pd.Series(0.0, index=f.index)

    # A cohesive multi-account cluster is the classic ring signature.
    score += (f["component_size"] >= 5).astype(float) * 0.45
    score += (f["community_size"] >= 4).astype(float) * 0.15

    # Sharing a strong identifier (inbox, phone, device, card) with others.
    score += (f["n_strong_links"] >= 4).astype(float) * 0.20

    # Own and neighbour claim behaviour.
    score += (f["claim_rate"] >= 0.30).astype(float) * 0.25
    score += (f["neighbour_claim_rate"] >= 0.25).astype(float) * 0.25

    # Tight signup burst.
    score += (f["signup_burst_24h"] >= 2).astype(float) * 0.15

    return score.clip(0.0, 1.0)


RULE_DESCRIPTIONS = [
    ("component_size >= 5", 0.45),
    ("community_size >= 4", 0.15),
    ("n_strong_links >= 4", 0.20),
    ("claim_rate >= 0.30", 0.25),
    ("neighbour_claim_rate >= 0.25", 0.25),
    ("signup_burst_24h >= 2", 0.15),
]

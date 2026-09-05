"""Rupee cost of an operating point.

F1 is not a business objective. A payments risk team chooses a threshold by
asking what it costs to be wrong in each direction, and those costs are wildly
asymmetric: a missed abuser costs one refund, while a wrongly restricted
customer costs their remaining lifetime value plus a support contact plus the
reputational tail.

This module converts a score distribution into a rupee curve and picks the
operating point that maximises net benefit, rather than the one that maximises
a symmetric statistic nobody in the business cares about.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import COSTS, CostModel
from .metrics import confusion_at


def cost_curve(
    y_true: np.ndarray,
    scores: np.ndarray,
    costs: CostModel | None = None,
    n_points: int = 101,
) -> pd.DataFrame:
    """Net rupee benefit across the full threshold range."""
    costs = costs or COSTS
    rows = []
    for threshold in np.linspace(0.01, 0.99, n_points):
        cm = confusion_at(y_true, scores, threshold)
        net = (
            cm.tp * costs.true_positive_recovery_inr
            - cm.fp * costs.false_positive_cost_inr
        )
        rows.append(
            {
                "threshold": round(float(threshold), 4),
                "tp": cm.tp,
                "fp": cm.fp,
                "fn": cm.fn,
                "precision": round(cm.precision, 4),
                "recall": round(cm.recall, 4),
                "net_benefit_inr": round(net, 2),
                "missed_loss_inr": round(cm.fn * costs.false_negative_cost_inr, 2),
                "fp_cost_inr": round(cm.fp * costs.false_positive_cost_inr, 2),
            }
        )
    return pd.DataFrame(rows)


def optimal_threshold(curve: pd.DataFrame) -> float:
    return float(curve.loc[curve["net_benefit_inr"].idxmax(), "threshold"])


def banded_policy(
    y_true: np.ndarray,
    scores: np.ndarray,
    review_threshold: float,
    action_threshold: float,
    costs: CostModel | None = None,
    reviewer_accuracy: float = 0.93,
) -> dict[str, float]:
    """Evaluate the three-band policy the system actually ships with.

    * score >= action_threshold        -> bounded automatic action
    * review_threshold <= score < high -> queued for a human
    * below                            -> allowed

    The middle band is where most of the value is. Sending an uncertain account
    to a person costs a fixed review fee but converts most of what would have
    been an expensive false positive into a correct decision. `reviewer_accuracy`
    is an assumption, not a measurement, and is stated as such in the model card.
    """
    costs = costs or COSTS
    actual = y_true.astype(bool)

    auto = scores >= action_threshold
    review = (scores >= review_threshold) & ~auto

    tp_auto = int(np.sum(auto & actual))
    fp_auto = int(np.sum(auto & ~actual))
    n_review = int(np.sum(review))
    tp_review = int(np.sum(review & actual))
    fp_review = int(np.sum(review & ~actual))
    missed = int(np.sum(~auto & ~review & actual))

    # A reviewer catches most of the true abusers in the band and clears most
    # of the innocents; the remainder fall through at full cost.
    caught_in_review = tp_review * reviewer_accuracy
    wrongly_actioned_in_review = fp_review * (1 - reviewer_accuracy)

    net = (
        (tp_auto + caught_in_review) * costs.true_positive_recovery_inr
        - (fp_auto + wrongly_actioned_in_review) * costs.false_positive_cost_inr
        - n_review * costs.manual_review_cost_inr
    )

    return {
        "review_threshold": review_threshold,
        "action_threshold": action_threshold,
        "auto_actioned": int(np.sum(auto)),
        "auto_true_positives": tp_auto,
        "auto_false_positives": fp_auto,
        "auto_precision": round(tp_auto / max(1, tp_auto + fp_auto), 4),
        "queued_for_review": n_review,
        "review_queue_true_positives": tp_review,
        "missed": missed,
        "recall_including_review": round(
            (tp_auto + caught_in_review) / max(1, int(actual.sum())), 4
        ),
        "net_benefit_inr": round(net, 2),
        "review_cost_inr": round(n_review * costs.manual_review_cost_inr, 2),
    }

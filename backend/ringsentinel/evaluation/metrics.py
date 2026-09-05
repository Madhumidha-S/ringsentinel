"""Classification metrics, reported per adversary level.

The headline number for any fraud model is close to meaningless on its own.
A model can post an excellent overall F1 purely by catching naive rings while
missing every sophisticated one - and the sophisticated ones are where the
money is. Every function here therefore supports stratification by evasion
level, and the report always shows the breakdown next to the headline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score


@dataclass
class ConfusionMetrics:
    threshold: float
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def false_positive_rate(self) -> float:
        return self.fp / (self.fp + self.tn) if (self.fp + self.tn) else 0.0

    def as_dict(self) -> dict:
        d = asdict(self)
        d.update(
            precision=round(self.precision, 4),
            recall=round(self.recall, 4),
            f1=round(self.f1, 4),
            false_positive_rate=round(self.false_positive_rate, 5),
        )
        return d


def confusion_at(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> ConfusionMetrics:
    pred = scores >= threshold
    actual = y_true.astype(bool)
    return ConfusionMetrics(
        threshold=float(threshold),
        tp=int(np.sum(pred & actual)),
        fp=int(np.sum(pred & ~actual)),
        fn=int(np.sum(~pred & actual)),
        tn=int(np.sum(~pred & ~actual)),
    )


def ranking_metrics(y_true: np.ndarray, scores: np.ndarray) -> dict[str, float]:
    """Threshold-free quality. Average precision is the honest headline for an
    imbalanced problem; ROC AUC is reported because reviewers expect it, but it
    flatters imbalanced classifiers and should not drive decisions."""
    out = {"average_precision": float(average_precision_score(y_true, scores))}
    try:
        out["roc_auc"] = float(roc_auc_score(y_true, scores))
    except ValueError:
        out["roc_auc"] = float("nan")
    out["prevalence"] = float(np.mean(y_true))
    return out


def pr_curve(y_true: np.ndarray, scores: np.ndarray, max_points: int = 300) -> pd.DataFrame:
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    # precision/recall are one longer than thresholds
    df = pd.DataFrame(
        {
            "threshold": np.append(thresholds, 1.0),
            "precision": precision,
            "recall": recall,
        }
    )
    if len(df) > max_points:
        df = df.iloc[:: len(df) // max_points].reset_index(drop=True)
    return df


def recall_by_level(
    y_true: np.ndarray, scores: np.ndarray, levels: np.ndarray, threshold: float
) -> pd.DataFrame:
    """Recall per adversary evasion level. The most important table we produce."""
    pred = scores >= threshold
    actual = y_true.astype(bool)
    rows = []
    for level in sorted({int(x) for x in levels if x >= 0}):
        mask = (levels == level) & actual
        n = int(mask.sum())
        if n == 0:
            continue
        caught = int(np.sum(pred & mask))
        rows.append(
            {
                "evasion_level": level,
                "ring_accounts": n,
                "caught": caught,
                "recall": round(caught / n, 4),
            }
        )
    return pd.DataFrame(rows)


def money_metrics(
    y_true: np.ndarray,
    scores: np.ndarray,
    threshold: float,
    exposure_inr: np.ndarray,
) -> dict[str, float]:
    """How much of the money at risk the operating point actually reaches.

    Account counts and rupees are different questions: catching many tiny
    abusers while missing the large ones is a bad outcome that a recall number
    hides completely.
    """
    pred = scores >= threshold
    actual = y_true.astype(bool)
    total_at_risk = float(exposure_inr[actual].sum())
    caught = float(exposure_inr[pred & actual].sum())
    return {
        "abuse_exposure_inr": round(total_at_risk, 2),
        "exposure_caught_inr": round(caught, 2),
        "exposure_recall": round(caught / total_at_risk, 4) if total_at_risk else 0.0,
        "legit_value_disrupted_inr": round(float(exposure_inr[pred & ~actual].sum()), 2),
    }

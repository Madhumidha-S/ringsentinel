"""Gradient-boosted account risk model.

Deliberately a boring model. The contribution of this project is the graph
features and the evaluation discipline, not the estimator; swapping in a
heavier model changes the numbers by little and the conclusions by nothing.

Probabilities are isotonically calibrated because every downstream decision is
a rupee threshold. An uncalibrated score can rank correctly and still put the
cost-optimal cutoff in the wrong place.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance

RANDOM_STATE = 20260904


@dataclass
class RingModel:
    estimator: CalibratedClassifierCV
    columns: list[str]
    train_prevalence: float

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        X = features[self.columns].to_numpy(dtype=float)
        return self.estimator.predict_proba(X)[:, 1]

    def save(self, path: Path) -> None:
        import pickle

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            pickle.dump(self, fh)
        path.with_suffix(".meta.json").write_text(
            json.dumps(
                {"columns": self.columns, "train_prevalence": self.train_prevalence}, indent=2
            )
        )

    @staticmethod
    def load(path: Path) -> RingModel:
        import pickle

        with path.open("rb") as fh:
            return pickle.load(fh)


def train_model(
    features: pd.DataFrame, labels: pd.Series, columns: list[str]
) -> RingModel:
    X = features[columns].to_numpy(dtype=float)
    y = labels.to_numpy(dtype=int)

    base = HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.06,
        max_leaf_nodes=31,
        min_samples_leaf=25,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.15,
        random_state=RANDOM_STATE,
    )
    # Isotonic calibration on cross-validated folds: the rupee threshold we
    # pick later is only meaningful if p=0.3 really means 30%.
    calibrated = CalibratedClassifierCV(base, method="isotonic", cv=4)
    calibrated.fit(X, y)

    return RingModel(
        estimator=calibrated,
        columns=list(columns),
        train_prevalence=float(y.mean()),
    )


def feature_importance(
    model: RingModel, features: pd.DataFrame, labels: pd.Series, n_repeats: int = 5
) -> pd.DataFrame:
    """Permutation importance on held-out data.

    Preferred over impurity importance, which is biased toward high-cardinality
    features and would flatter our graph columns.
    """
    X = features[model.columns].to_numpy(dtype=float)
    y = labels.to_numpy(dtype=int)
    result = permutation_importance(
        model.estimator, X, y, n_repeats=n_repeats, random_state=RANDOM_STATE,
        scoring="average_precision",
    )
    return (
        pd.DataFrame(
            {
                "feature": model.columns,
                "importance": result.importances_mean,
                "std": result.importances_std,
            }
        )
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )

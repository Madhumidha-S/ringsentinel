"""Time-ordered replay backtest.

The split is by account creation time, not at random:

    train : accounts created on or before day T, featurised **as of day T**
    test  : accounts created after day T, featurised as of the scoring day

No account appears in both sets, and no training feature can see anything that
happened after day T. This mirrors deployment - fit on what you knew then,
score accounts you had not met yet - and it costs real accuracy compared with a
random split. A random split on this dataset scores materially better and is
wrong, because graph features leak future co-membership across the split.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..config import COSTS
from ..detect.model import RingModel, feature_importance, train_model
from ..detect.rules import rule_scores
from ..graph.build import IdentityGraph
from ..graph.communities import Communities
from ..graph.features import build_features, feature_columns
from . import cost as cost_mod
from . import metrics as met

SECONDS_PER_DAY = 86_400


@dataclass
class ReplayResult:
    train_cutoff_day: int
    score_day: int
    n_train: int
    n_test: int
    model: RingModel
    test_features: pd.DataFrame
    y_true: np.ndarray
    model_scores: np.ndarray
    rule_scores: np.ndarray
    levels: np.ndarray
    identity: IdentityGraph
    communities: Communities
    report: dict[str, Any] = field(default_factory=dict)


def run_replay(
    dataset,
    train_cutoff_day: int = 70,
    score_day: int = 120,
    verbose: bool = True,
) -> ReplayResult:
    accounts, orders, claims = dataset.accounts, dataset.orders, dataset.claims
    t0 = dataset.meta["t0"]
    t_train = t0 + train_cutoff_day * SECONDS_PER_DAY
    t_score = t0 + score_day * SECONDS_PER_DAY

    label_map = accounts.set_index("account_id")["label_is_ring"].to_dict()
    level_map = accounts.set_index("account_id")["label_evasion_level"].to_dict()
    created_map = accounts.set_index("account_id")["created_ts"].to_dict()

    # ---- training fold: everything known at the cutoff ----
    train_feats, _, _ = build_features(accounts, orders, claims, as_of=t_train)
    cols = feature_columns(train_feats)
    y_train = train_feats["account_id"].map(label_map).astype(int)
    if verbose:
        print(f"  train: {len(train_feats):,} accounts as of day {train_cutoff_day} "
              f"(prevalence {y_train.mean():.2%})")

    model = train_model(train_feats, y_train, cols)

    # ---- test fold: accounts first seen after the cutoff ----
    all_feats, identity, communities = build_features(accounts, orders, claims, as_of=t_score)
    is_new = all_feats["account_id"].map(created_map) > t_train
    test_feats = all_feats[is_new].reset_index(drop=True)
    y_test = test_feats["account_id"].map(label_map).astype(int).to_numpy()
    levels = test_feats["account_id"].map(level_map).fillna(-1).to_numpy()
    if verbose:
        print(f"  test : {len(test_feats):,} accounts created after day {train_cutoff_day}, "
              f"scored as of day {score_day} (prevalence {y_test.mean():.2%})")

    model_p = model.predict_proba(test_feats)
    rules_p = rule_scores(test_feats).to_numpy()

    # ---- reporting ----
    curve = cost_mod.cost_curve(y_test, model_p, COSTS)
    best_t = cost_mod.optimal_threshold(curve)
    cm = met.confusion_at(y_test, model_p, best_t)

    rules_curve = cost_mod.cost_curve(y_test, rules_p, COSTS)
    rules_t = cost_mod.optimal_threshold(rules_curve)
    rules_cm = met.confusion_at(y_test, rules_p, rules_t)

    exposure = test_feats["claimed_amount"].to_numpy(dtype=float)

    report: dict[str, Any] = {
        "split": {
            "train_cutoff_day": train_cutoff_day,
            "score_day": score_day,
            "n_train": int(len(train_feats)),
            "n_test": int(len(test_feats)),
            "test_prevalence": round(float(y_test.mean()), 4),
        },
        "model": {
            **{k: round(v, 4) for k, v in met.ranking_metrics(y_test, model_p).items()},
            "cost_optimal_threshold": best_t,
            "at_cost_optimal": cm.as_dict(),
            "net_benefit_inr": float(curve["net_benefit_inr"].max()),
            **met.money_metrics(y_test, model_p, best_t, exposure),
        },
        "rules_baseline": {
            **{k: round(v, 4) for k, v in met.ranking_metrics(y_test, rules_p).items()},
            "cost_optimal_threshold": rules_t,
            "at_cost_optimal": rules_cm.as_dict(),
            "net_benefit_inr": float(rules_curve["net_benefit_inr"].max()),
        },
        "recall_by_evasion_level": met.recall_by_level(
            y_test, model_p, levels, best_t
        ).to_dict("records"),
        "rules_recall_by_evasion_level": met.recall_by_level(
            y_test, rules_p, levels, rules_t
        ).to_dict("records"),
        "banded_policy": cost_mod.banded_policy(
            y_test, model_p, review_threshold=max(0.05, best_t * 0.4),
            action_threshold=min(0.95, best_t * 1.6),
        ),
        "cost_curve": curve.to_dict("records"),
        "pr_curve": met.pr_curve(y_test, model_p).to_dict("records"),
    }

    try:
        imp = feature_importance(model, test_feats, pd.Series(y_test), n_repeats=4)
        report["feature_importance"] = imp.head(20).to_dict("records")
    except Exception as exc:  # pragma: no cover - diagnostics only
        report["feature_importance_error"] = str(exc)

    return ReplayResult(
        train_cutoff_day=train_cutoff_day,
        score_day=score_day,
        n_train=len(train_feats),
        n_test=len(test_feats),
        model=model,
        test_features=test_feats,
        y_true=y_test,
        model_scores=model_p,
        rule_scores=rules_p,
        levels=levels,
        identity=identity,
        communities=communities,
        report=report,
    )

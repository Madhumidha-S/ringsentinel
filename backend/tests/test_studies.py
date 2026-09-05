"""The robustness studies must themselves be correct, or they mislead."""

from __future__ import annotations

import numpy as np
import pytest

from ringsentinel.evaluation.studies import ABLATION_SETS, prevalence_sensitivity
from ringsentinel.graph.features import FEATURE_FAMILIES, family_columns


def test_feature_families_partition_the_feature_set(small_dataset):
    """Every feature belongs to exactly one family.

    If a family is missing a column, the ablation quietly understates what the
    excluded set could do, and the conclusion drawn from it is wrong.
    """
    from ringsentinel.graph.features import build_features, feature_columns

    features, _, _ = build_features(
        small_dataset.accounts, small_dataset.orders, small_dataset.claims,
        small_dataset.orders["ts"].max(),
    )
    actual = set(feature_columns(features))
    covered: list[str] = []
    for cols in FEATURE_FAMILIES.values():
        covered.extend(cols)

    assert len(covered) == len(set(covered)), "a feature appears in two families"
    assert set(covered) == actual, (
        f"family coverage mismatch; "
        f"missing={actual - set(covered)} unknown={set(covered) - actual}"
    )


def test_ablation_sets_reference_real_families():
    for name, families in ABLATION_SETS.items():
        cols = family_columns(families)
        assert cols, f"ablation set {name} resolves to no columns"


def test_family_columns_rejects_an_unknown_family():
    with pytest.raises(KeyError, match="unknown feature family"):
        family_columns(["not_a_family"])


class _FakeResult:
    """Minimal stand-in so the prevalence maths is tested without a full replay."""

    def __init__(self, y, scores, threshold):
        self.y_true = np.asarray(y)
        self.model_scores = np.asarray(scores)
        self.report = {"model": {"cost_optimal_threshold": threshold}}


def test_prevalence_subsampling_hits_the_target_rate():
    rng = np.random.default_rng(0)
    y = np.array([1] * 400 + [0] * 6000)
    scores = np.concatenate([rng.uniform(0.6, 1.0, 400), rng.uniform(0.0, 0.4, 6000)])
    out = prevalence_sensitivity(_FakeResult(y, scores, 0.5), targets=(0.01, 0.05),
                                 n_bootstrap=20)
    for row in out["results"]:
        assert abs(row["achieved_prevalence"] - row["target_prevalence"]) < 0.002


def test_lower_prevalence_lowers_precision_but_not_recall():
    """The whole point of the study, asserted.

    Subsampling positives leaves recall an unbiased estimate and makes
    precision worse, because the negatives are unchanged.
    """
    rng = np.random.default_rng(1)
    y = np.array([1] * 400 + [0] * 6000)
    # An imperfect classifier, so there are false positives to dilute with.
    scores = np.concatenate([rng.uniform(0.4, 1.0, 400), rng.uniform(0.0, 0.6, 6000)])
    out = prevalence_sensitivity(_FakeResult(y, scores, 0.5), targets=(0.01, 0.0625),
                                 n_bootstrap=60)
    low, high = out["results"][0], out["results"][1]
    assert low["precision_mean"] < high["precision_mean"], (
        "precision must degrade as prevalence falls"
    )
    assert abs(low["recall_mean"] - high["recall_mean"]) < 0.05, (
        "recall should be roughly invariant to positive subsampling"
    )


def test_prevalence_study_reports_confidence_intervals():
    rng = np.random.default_rng(2)
    y = np.array([1] * 200 + [0] * 3000)
    scores = np.concatenate([rng.uniform(0.5, 1.0, 200), rng.uniform(0.0, 0.5, 3000)])
    out = prevalence_sensitivity(_FakeResult(y, scores, 0.5), targets=(0.02,),
                                 n_bootstrap=50)
    row = out["results"][0]
    assert row["precision_p2_5"] <= row["precision_mean"] <= row["precision_p97_5"]

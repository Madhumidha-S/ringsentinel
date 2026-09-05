"""The leakage guarantees this project's numbers depend on.

If any of these fail, every metric in the README is void.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ringsentinel.graph.features import LABEL_COLUMNS, build_features, feature_columns

SECONDS_PER_DAY = 86_400


def test_no_label_column_reaches_the_model(small_dataset):
    as_of = small_dataset.orders["ts"].max()
    features, _, _ = build_features(
        small_dataset.accounts, small_dataset.orders, small_dataset.claims, as_of
    )
    cols = feature_columns(features)
    for banned in LABEL_COLUMNS:
        assert banned not in cols, f"label column {banned} leaked into the feature set"
    assert "account_id" not in cols


def test_features_are_invariant_to_future_data(small_dataset):
    """The core temporal guarantee.

    Features computed as of day T must be byte-identical whether or not the
    input frames also contain events after T. If they differ, some aggregate
    is reading the future and every backtest number is inflated.
    """
    t0 = small_dataset.meta["t0"]
    cutoff = t0 + 50 * SECONDS_PER_DAY

    full, _, _ = build_features(
        small_dataset.accounts, small_dataset.orders, small_dataset.claims, cutoff
    )

    truncated_orders = small_dataset.orders[small_dataset.orders["ts"] <= cutoff]
    truncated_claims = small_dataset.claims[small_dataset.claims["ts"] <= cutoff]
    truncated_accounts = small_dataset.accounts[small_dataset.accounts["created_ts"] <= cutoff]
    truncated, _, _ = build_features(
        truncated_accounts, truncated_orders, truncated_claims, cutoff
    )

    full = full.sort_values("account_id").reset_index(drop=True)
    truncated = truncated.sort_values("account_id").reset_index(drop=True)

    assert list(full["account_id"]) == list(truncated["account_id"])
    pd.testing.assert_frame_equal(full, truncated, check_exact=False, rtol=1e-9)


def test_accounts_created_after_cutoff_are_excluded(small_dataset):
    t0 = small_dataset.meta["t0"]
    cutoff = t0 + 30 * SECONDS_PER_DAY
    features, _, _ = build_features(
        small_dataset.accounts, small_dataset.orders, small_dataset.claims, cutoff
    )
    created = small_dataset.accounts.set_index("account_id")["created_ts"]
    assert (created.loc[features["account_id"]] <= cutoff).all()


def test_no_feature_is_a_perfect_label_proxy(small_dataset):
    """Guards against a generator artefact that makes one column the answer.

    A single feature that separates the classes perfectly means the benchmark
    is broken, not that the model is good.
    """
    as_of = small_dataset.orders["ts"].max()
    features, _, _ = build_features(
        small_dataset.accounts, small_dataset.orders, small_dataset.claims, as_of
    )
    merged = features.merge(
        small_dataset.accounts[["account_id", "label_is_ring"]], on="account_id"
    )
    y = merged["label_is_ring"].to_numpy(dtype=bool)

    for col in feature_columns(features):
        values = merged[col].to_numpy(dtype=float)
        if np.std(values) == 0:
            continue
        # Best achievable accuracy from a single threshold on this feature.
        order = np.argsort(values)
        sorted_y = y[order]
        cum_pos = np.cumsum(sorted_y)
        total_pos = sorted_y.sum()
        n = len(sorted_y)
        idx = np.arange(1, n + 1)
        # Predict positive above the split point.
        tp = total_pos - cum_pos
        fp = (n - idx) - tp
        fn = cum_pos
        f1 = 2 * tp / np.maximum(1, 2 * tp + fp + fn)
        assert f1.max() < 0.98, (
            f"feature {col!r} alone achieves F1 {f1.max():.3f} - "
            "the generator is leaking the label through this column"
        )

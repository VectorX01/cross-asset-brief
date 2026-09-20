"""Pins the computed numbers so a refactor cannot silently change them."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from brief.metrics import cross_asset  # noqa: F401
from brief.pipeline import build_payload

GOLDEN = Path(__file__).parent / "fixtures" / "golden_payload.json"

# The three cross-asset metrics, all of which the frozen inputs below feed
# completely: every one of them pins a real number, none records as null.
# comovement needs the whole six-series basket, so the fixture supplies all
# six -- a null there would assert only that the metric stays broken, and
# comovement is the one metric whose value depends on the differencing rule
# being applied per series kind.
# Filtering explicitly (rather than deriving from every registered metric)
# keeps this test independent of test collection order: other test modules
# (e.g. test_metrics_positioning.py) import brief.metrics.positioning, which
# registers five more metrics into the module-global REGISTRY, and pytest
# runs every test module in one process.
GOLDEN_METRICS = ("stock_bond", "credit_vs_vol", "comovement")


def frozen_levels():
    idx = pd.bdate_range("2018-01-01", periods=1500)
    rng = np.random.default_rng(42)
    shock = rng.normal(size=1500)
    independent = rng.normal(size=1500)
    # ust10 blends the shared shock with an independent draw so stock_bond
    # lands mid-range rather than saturating at the +-1.0 clamp boundary
    # (R19): a value pinned exactly at the boundary can't distinguish the
    # real metric from a regression that dropped differencing entirely.
    return {
        "equity": pd.Series(100 * np.exp(np.cumsum(shock * 0.01)), index=idx),
        "ust10": pd.Series(4.0 + np.cumsum((shock * 0.6 + independent * 0.8) * 0.02), index=idx),
        "credit": pd.Series(4.0 + np.cumsum(rng.normal(size=1500) * 0.01), index=idx),
        "vix": pd.Series(18.0 + np.cumsum(rng.normal(size=1500) * 0.05), index=idx),
        # usd and wti complete the comovement basket. Both are price-like in
        # SERIES, and each blends the shared shock with an independent draw so
        # the pinned correlation lands mid-range rather than at 0 or 1, where
        # a differencing regression could hide.
        "usd": pd.Series(
            100 * np.exp(np.cumsum((shock * -0.4 + rng.normal(size=1500) * 0.9) * 0.004)),
            index=idx,
        ),
        "wti": pd.Series(
            70 * np.exp(np.cumsum((shock * 0.5 + rng.normal(size=1500) * 0.9) * 0.02)),
            index=idx,
        ),
    }


def computed():
    payload = build_payload(frozen_levels())
    return {
        tile.name: None if tile.error else round(tile.value, 8)
        for tile in payload["tiles"]
        if tile.name in GOLDEN_METRICS
    }


def test_every_golden_metric_pins_a_number_not_a_null():
    # A null pins only that the metric is broken. comovement recorded as null
    # for exactly that reason, which is how the differencing rule went
    # unprotected: the one metric that depends on it asserted nothing.
    actual = computed()
    assert set(actual) == set(GOLDEN_METRICS)
    assert all(value is not None for value in actual.values()), actual


def test_computed_values_match_the_golden_file():
    # Every mismatch is collected before asserting, rather than failing on the
    # first: when a shared transform drifts it moves several metrics at once,
    # and the useful signal is which ones.
    expected = json.loads(GOLDEN.read_text())
    actual = computed()
    assert actual.keys() == expected.keys()
    drifted = {
        name: {"computed": actual[name], "golden": value}
        for name, value in expected.items()
        if actual[name] != pytest.approx(value, abs=1e-8)
    }
    assert not drifted, f"computed values no longer match the golden file: {drifted}"

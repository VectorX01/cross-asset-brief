"""Pins the computed numbers so a refactor cannot silently change them."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from brief.metrics import cross_asset  # noqa: F401
from brief.pipeline import build_payload

GOLDEN = Path(__file__).parent / "fixtures" / "golden_payload.json"

# Only the three cross-asset metrics the frozen inputs below actually support.
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
    }


def computed():
    payload = build_payload(frozen_levels())
    return {
        tile.name: None if tile.error else round(tile.value, 8)
        for tile in payload["tiles"]
        if tile.name in GOLDEN_METRICS
    }


def test_computed_values_match_the_golden_file():
    expected = json.loads(GOLDEN.read_text())
    actual = computed()
    assert actual.keys() == expected.keys()
    for name, value in expected.items():
        if value is None:
            assert actual[name] is None
        else:
            assert actual[name] == pytest.approx(value, abs=1e-8)

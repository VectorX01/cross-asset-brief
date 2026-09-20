import numpy as np
import pandas as pd
import pytest

from brief.metrics import cross_asset  # noqa: F401  (registers the metrics)
from brief.metrics.registry import REGISTRY, Metric, register


def dates(n):
    return pd.bdate_range("2015-01-01", periods=n)


def test_register_rejects_a_metric_without_an_interpretation():
    with pytest.raises(TypeError):
        Metric(
            name="x",
            title="X",
            inputs=("equity",),
            context_window=None,
            fn=lambda levels: pd.Series(dtype=float),
            unit="",
        )


def test_register_rejects_a_duplicate_name():
    metric = REGISTRY["stock_bond"]
    with pytest.raises(ValueError, match="duplicate"):
        register(metric)


def test_stock_bond_is_positive_when_equities_and_yields_move_together():
    rng = np.random.default_rng(0)
    shock = rng.normal(size=200)
    trend = np.linspace(0.0, 1.0, 200)
    equity = pd.Series(100 * np.exp(np.cumsum(shock * 0.01) + trend * 0.5), index=dates(200))
    yields = pd.Series(4.0 + np.cumsum(shock * 0.02) - trend * 3.0, index=dates(200))
    out = REGISTRY["stock_bond"].fn({"equity": equity, "ust10": yields})
    assert out.iloc[-1] > 0.9


def test_stock_bond_is_negative_when_they_move_inversely():
    rng = np.random.default_rng(1)
    shock = rng.normal(size=200)
    trend = np.linspace(0.0, 1.0, 200)
    equity = pd.Series(100 * np.exp(np.cumsum(shock * 0.01) + trend * 0.5), index=dates(200))
    yields = pd.Series(4.0 - np.cumsum(shock * 0.02) + trend * 3.0, index=dates(200))
    out = REGISTRY["stock_bond"].fn({"equity": equity, "ust10": yields})
    assert out.iloc[-1] < -0.9


def test_stock_bond_interpretation_names_the_regime():
    positive = REGISTRY["stock_bond"].interpret(0.41, 94.0)
    negative = REGISTRY["stock_bond"].interpret(-0.55, 6.0)
    assert "not hedging" in positive
    assert "hedging" in negative and "not hedging" not in negative
    assert "+0.41" in positive

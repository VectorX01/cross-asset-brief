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


def test_credit_vs_vol_is_positive_when_credit_is_the_stressed_one():
    idx = pd.bdate_range("2015-01-01", periods=1400)
    credit = pd.Series(np.linspace(3.0, 9.0, 1400), index=idx)
    vix = pd.Series(np.linspace(30.0, 12.0, 1400), index=idx)
    out = REGISTRY["credit_vs_vol"].fn({"credit": credit, "vix": vix})
    assert out.iloc[-1] > 50


def test_credit_vs_vol_is_negative_when_equity_vol_is_the_stressed_one():
    idx = pd.bdate_range("2015-01-01", periods=1400)
    credit = pd.Series(np.linspace(9.0, 3.0, 1400), index=idx)
    vix = pd.Series(np.linspace(12.0, 30.0, 1400), index=idx)
    out = REGISTRY["credit_vs_vol"].fn({"credit": credit, "vix": vix})
    assert out.iloc[-1] < -50


def test_credit_vs_vol_interpretation_names_the_stressed_market():
    assert "credit" in REGISTRY["credit_vs_vol"].interpret(62.0, 91.0).lower()
    assert "vol" in REGISTRY["credit_vs_vol"].interpret(-62.0, 8.0).lower()


def test_comovement_is_high_when_every_asset_shares_one_driver():
    idx = pd.bdate_range("2015-01-01", periods=300)
    rng = np.random.default_rng(3)
    shock = rng.normal(size=300)
    levels = {
        "equity": pd.Series(100 * np.exp(np.cumsum(shock * 0.01)), index=idx),
        "ust10": pd.Series(4.0 + np.cumsum(shock * 0.02), index=idx),
        "usd": pd.Series(100 * np.exp(np.cumsum(shock * 0.005)), index=idx),
        "credit": pd.Series(4.0 + np.cumsum(shock * 0.01), index=idx),
        "wti": pd.Series(70 * np.exp(np.cumsum(shock * 0.02)), index=idx),
        "vix": pd.Series(18.0 + np.cumsum(shock * 0.05), index=idx),
    }
    out = REGISTRY["comovement"].fn(levels)
    assert out.iloc[-1] > 0.9


def test_comovement_is_low_when_assets_are_independent():
    idx = pd.bdate_range("2015-01-01", periods=300)
    rng = np.random.default_rng(4)
    levels = {
        name: pd.Series(100 + np.cumsum(rng.normal(size=300)), index=idx)
        for name in ("equity", "ust10", "usd", "credit", "wti", "vix")
    }
    out = REGISTRY["comovement"].fn(levels)
    assert out.iloc[-1] < 0.4


def test_comovement_middle_branch_is_neutral_not_a_dismissal():
    # A mid-percentile reading can still be the day's most unusual metric once
    # ranked against the other eight -- the sentence must not tell the reader
    # it is unremarkable while the ranker highlights it as notable.
    sentence = REGISTRY["comovement"].interpret(0.34, 50.0)
    lowered = sentence.lower()
    assert "unremarkable" not in lowered
    assert "not working" not in lowered
    assert "dominates" not in lowered
    assert "50th" in sentence
    assert "0.34" in sentence

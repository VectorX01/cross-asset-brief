import numpy as np
import pandas as pd

from brief.metrics import positioning  # noqa: F401
from brief.metrics.registry import REGISTRY


def weekly(n):
    return pd.date_range("2018-01-02", periods=n, freq="W-TUE")


def test_a_positioning_metric_exists_for_every_contract():
    from brief.config import CONTRACTS

    for key in CONTRACTS:
        assert f"pos_{key}" in REGISTRY


def test_positioning_metric_returns_the_net_position_series():
    net = pd.Series(np.arange(200, dtype=float), index=weekly(200))
    out = REGISTRY["pos_es"].fn({"cot_es": net})
    assert out.iloc[-1] == 199.0


def test_positioning_interpretation_calls_out_crowding():
    assert "crowded" in REGISTRY["pos_es"].interpret(120000.0, 96.0).lower()
    assert "crowded" in REGISTRY["pos_es"].interpret(-90000.0, 3.0).lower()
    assert "crowded" not in REGISTRY["pos_es"].interpret(1000.0, 50.0).lower()


def test_divergence_is_positive_when_positioning_is_long_into_weak_price():
    idx = pd.bdate_range("2019-01-01", periods=900)
    price = pd.Series(np.linspace(120.0, 90.0, 900), index=idx)
    net = pd.Series(np.linspace(-50000.0, 90000.0, 200), index=weekly(200))
    out = REGISTRY["divergence"].fn({"cot_es": net, "spx": price})
    assert out.iloc[-1] > 50


def test_divergence_is_negative_when_positioning_is_short_into_strong_price():
    idx = pd.bdate_range("2019-01-01", periods=900)
    price = pd.Series(np.linspace(90.0, 120.0, 900), index=idx)
    net = pd.Series(np.linspace(90000.0, -50000.0, 200), index=weekly(200))
    out = REGISTRY["divergence"].fn({"cot_es": net, "spx": price})
    assert out.iloc[-1] < -50


def test_divergence_interpretation_describes_the_setup():
    assert "sponsorship" in REGISTRY["divergence"].interpret(70.0, 97.0).lower()
    assert "capitulation" in REGISTRY["divergence"].interpret(-70.0, 2.0).lower()

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


def test_each_contract_gets_its_own_label_and_series():
    from brief.config import CONTRACTS

    net_es = pd.Series(np.arange(200, dtype=float), index=weekly(200))
    net_wti = pd.Series(np.arange(200, dtype=float) * -1.0, index=weekly(200))
    levels = {"cot_es": net_es, "cot_wti": net_wti}

    assert REGISTRY["pos_es"].fn(levels).iloc[-1] == 199.0
    assert REGISTRY["pos_wti"].fn(levels).iloc[-1] == -199.0

    es_sentence = REGISTRY["pos_es"].interpret(199.0, 95.0)
    wti_sentence = REGISTRY["pos_wti"].interpret(-199.0, 95.0)
    assert CONTRACTS["es"].label in es_sentence
    assert CONTRACTS["wti"].label in wti_sentence
    assert CONTRACTS["wti"].label not in es_sentence


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


def test_divergence_interprets_by_percentile_not_raw_value():
    # A large raw spread that is only mid-pack relative to its own history is
    # not a trade setup -- the old value-based threshold called this "notable"
    # regardless of how unusual it actually was, contradicting the ranker.
    neutral = REGISTRY["divergence"].interpret(70.0, 50.0).lower()
    assert "sponsorship" not in neutral
    assert "capitulation" not in neutral

    # A modest raw spread that sits in the extreme tail of its own history IS
    # a trade setup -- this is exactly the case the old threshold missed.
    extreme = REGISTRY["divergence"].interpret(20.0, 95.0).lower()
    assert "sponsorship" in extreme


def test_divergence_middle_branch_is_neutral_not_a_dismissal():
    # A mid-percentile reading can still be the day's most unusual metric once
    # ranked against the other eight -- the sentence must not claim there is
    # nothing worth trading while the ranker highlights it as notable, nor
    # smuggle in the tail branches' trade language.
    sentence = REGISTRY["divergence"].interpret(70.0, 50.0)
    lowered = sentence.lower()
    assert "no divergence worth trading" not in lowered
    assert "sponsorship" not in lowered
    assert "capitulation" not in lowered
    assert "50th" in sentence

    near_zero = REGISTRY["divergence"].interpret(0.2, 50.0).lower()
    assert "longer" not in near_zero
    assert "shorter" not in near_zero


def test_positioning_sentence_derives_its_window_from_the_constant(monkeypatch):
    # The window was prose: "percentile of three years" as a string literal
    # that POSITIONING_WINDOW_YEARS did not control, so changing the constant
    # would have left the page asserting a window it no longer used.
    from brief.metrics import positioning as positioning_module

    assert "3 years" in REGISTRY["pos_es"].interpret(120000.0, 50.0)
    monkeypatch.setattr(positioning_module, "POSITIONING_WINDOW_YEARS", 7)
    sentence = REGISTRY["pos_es"].interpret(120000.0, 50.0)
    assert "7 years" in sentence
    assert "3 years" not in sentence


def test_the_trader_category_comes_from_the_report_each_contract_uses():
    # Financial futures are reported by the TFF report's leveraged funds;
    # physical commodities by the disaggregated report's managed money. Gold
    # and WTI positioning is managed money, and calling it leveraged funds is
    # the single most costly error this page could make to a front-office
    # reader.
    from brief.config import CONTRACTS

    assert CONTRACTS["es"].trader_category == "leveraged funds"
    assert CONTRACTS["ust10"].trader_category == "leveraged funds"
    assert CONTRACTS["dxy"].trader_category == "leveraged funds"
    assert CONTRACTS["gold"].trader_category == "managed money"
    assert CONTRACTS["wti"].trader_category == "managed money"


def test_a_positioning_tile_names_its_trader_category():
    assert "managed money" in REGISTRY["pos_gold"].title
    assert "managed money" in REGISTRY["pos_gold"].interpret(133116.0, 87.0)
    assert "leveraged" not in REGISTRY["pos_gold"].interpret(133116.0, 87.0).lower()

    assert "leveraged funds" in REGISTRY["pos_es"].title
    assert "leveraged funds" in REGISTRY["pos_es"].interpret(120000.0, 50.0)


def test_divergence_takes_its_trader_category_from_the_contract_too():
    from brief.config import CONTRACTS
    from brief.metrics.positioning import DIVERGENCE_CONTRACT

    category = CONTRACTS[DIVERGENCE_CONTRACT].trader_category
    for value, pctile in ((70.0, 97.0), (-70.0, 2.0), (0.2, 50.0), (30.0, 50.0)):
        assert category.lower() in REGISTRY["divergence"].interpret(value, pctile).lower()


def test_divergence_tails_never_contradict_their_own_number():
    # The tail branches asserted a direction from the percentile alone. A
    # high percentile on a negative spread would have produced "are -20
    # percentile points longer than price justifies" -- a sentence arguing
    # with the number printed directly above it.
    long_tail = REGISTRY["divergence"].interpret(-20.0, 96.0).lower()
    assert "longer" not in long_tail
    assert "sponsorship" not in long_tail
    assert "shorter" in long_tail
    assert "96th" in long_tail

    short_tail = REGISTRY["divergence"].interpret(30.0, 3.0).lower()
    assert "shorter" not in short_tail
    assert "capitulation" not in short_tail
    assert "longer" in short_tail
    assert "3rd" in short_tail

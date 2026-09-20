"""The series catalogue: what a series is, where it comes from, how it's quoted."""

import pytest

from brief.config import QUOTES, SERIES, SeriesDef, source_of
from brief.transforms import PRICE_LIKE, RATE_LIKE


def test_a_series_defaults_to_fred_because_most_of_them_are():
    assert SeriesDef("DGS10", "10y", RATE_LIKE).source == "FRED"


def test_a_series_can_declare_a_different_source():
    assert SeriesDef("GC=F", "Gold", PRICE_LIKE, source="YAHOO").source == "YAHOO"


def test_an_unknown_source_is_rejected_rather_than_silently_never_fetched():
    with pytest.raises(ValueError, match="source"):
        SeriesDef("GC=F", "Gold", PRICE_LIKE, source="BLOOMBERG")


def test_source_of_reports_the_series_own_source_not_a_guess():
    assert source_of("ust10") == "FRED"
    assert source_of("gold") == "YAHOO"


def test_positioning_keys_still_resolve_to_the_cftc():
    assert source_of("cot_es") == "CFTC"


def test_an_unknown_key_is_an_error_not_a_default():
    with pytest.raises(KeyError):
        source_of("not_a_series")


def test_every_series_declares_a_quote_the_renderer_understands():
    unknown = {key: d.quote for key, d in SERIES.items() if d.quote not in QUOTES}
    assert unknown == {}


def test_prices_that_move_fast_are_not_sourced_from_fred():
    """FRED ran three days behind on a week crude fell ten percent, and it
    carries no free daily gold at all."""
    for key in ("spx", "equity", "crude", "gold"):
        assert SERIES[key].source == "YAHOO", key


def test_rates_and_credit_stay_on_fred_which_is_official_and_complete():
    for key in ("ust2", "ust10", "ust30", "real10", "be10", "sofr", "hy", "ig"):
        assert SERIES[key].source == "FRED", key

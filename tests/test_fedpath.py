"""Fed pricing from 30-day fed funds futures."""

from datetime import date

import pytest

from brief.fedpath import build_path, contract_symbol, implied_rate, next_contracts, summarise


def test_contract_symbols_use_the_cme_month_code():
    assert contract_symbol(2026, 12) == "ZQZ26.CBT"
    assert contract_symbol(2027, 1) == "ZQF27.CBT"
    assert contract_symbol(2027, 3) == "ZQH27.CBT"


def test_the_contract_run_starts_next_month_not_this_one():
    """Most of the current month has already fixed, so its implied average
    describes where the rate has been rather than where it is going."""
    labels = [label for label, _ in next_contracts(date(2026, 11, 6), 3)]
    assert labels == ["Dec 2026", "Jan 2027", "Feb 2027"]


def test_the_run_rolls_over_a_year_end():
    symbols = [sym for _, sym in next_contracts(date(2026, 11, 6), 3)]
    assert symbols == ["ZQZ26.CBT", "ZQF27.CBT", "ZQG27.CBT"]


def test_implied_rate_is_a_hundred_minus_the_price():
    assert implied_rate(95.94) == pytest.approx(4.06)


def test_the_path_prices_the_change_against_the_current_rate():
    prices = {"ZQZ26.CBT": 96.00, "ZQF27.CBT": 95.94}
    path = build_path(date(2026, 11, 6), 2, lambda s: prices[s], current=4.00)
    assert [p.label for p in path] == ["Dec 2026", "Jan 2027"]
    assert path[0].change_bp == pytest.approx(0.0, abs=1e-6)
    assert path[1].change_bp == pytest.approx(6.0, abs=1e-6)


def test_a_contract_that_will_not_fetch_is_left_out_rather_than_faked():
    def flaky(symbol):
        if symbol == "ZQF27.CBT":
            raise RuntimeError("HTTP 404")
        return 96.00

    path = build_path(date(2026, 11, 6), 2, flaky, current=4.00)
    assert [p.label for p in path] == ["Dec 2026"]


def test_with_no_current_rate_the_level_still_shows_but_the_change_does_not():
    path = build_path(date(2026, 11, 6), 1, lambda s: 96.00, current=None)
    assert path[0].implied == pytest.approx(4.00)
    assert path[0].change_bp is None


def test_the_summary_names_hikes_when_the_path_rises():
    # Z26/F27/G27 are Dec/Jan/Feb -- the three the run actually asks for.
    prices = {"ZQZ26.CBT": 96.00, "ZQF27.CBT": 95.94, "ZQG27.CBT": 95.87}
    path = build_path(date(2026, 11, 6), 3, lambda s: prices[s], current=4.00)
    assert summarise(path) == "13bp of hikes priced by Feb 2027."


def test_the_summary_names_cuts_when_the_path_falls():
    path = build_path(date(2026, 11, 6), 1, lambda s: 96.50, current=4.00)
    assert summarise(path) == "50bp of cuts priced by Dec 2026."


def test_a_flat_path_says_nothing_is_priced_rather_than_rounding_to_a_claim():
    path = build_path(date(2026, 11, 6), 1, lambda s: 96.02, current=4.00)
    assert "Nothing meaningful priced" in summarise(path)


def test_an_empty_path_does_not_raise():
    assert "No fed funds pricing" in summarise([])

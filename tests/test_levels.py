"""The levels board: what a number is, what it just did, and its recent range."""

import numpy as np
import pandas as pd
import pytest

from brief.levels import BoardRow, board_row, build_board
from brief.transforms import PRICE_LIKE, RATE_LIKE


def daily(values, end="2026-09-18"):
    """A business-day series ending on `end`, oldest first."""
    idx = pd.bdate_range(end=end, periods=len(values))
    return pd.Series([float(v) for v in values], index=idx)


def test_level_is_the_most_recent_observation():
    row = board_row(daily([1.0, 2.0, 3.5]), key="ust10", label="10y", kind=RATE_LIKE, quote="yield", stale_after_days=5)
    assert row.level == 3.5


def test_rate_like_change_is_a_difference_in_native_units():
    row = board_row(daily([4.00, 4.07]), key="ust10", label="10y", kind=RATE_LIKE, quote="yield", stale_after_days=5)
    assert row.change_1d == pytest.approx(0.07)


def test_price_like_change_is_a_percent_move():
    row = board_row(daily([100.0, 110.0]), key="spx", label="S&P 500", kind=PRICE_LIKE, quote="price", stale_after_days=5)
    assert row.change_1d == pytest.approx(10.0)


def test_month_change_reaches_back_a_calendar_month_not_a_row():
    # 60 business days is ~3 calendar months, so a row-based lookback would
    # pick a different point than a date-based one.
    series = daily(np.linspace(1.0, 61.0, 61))
    row = board_row(series, key="ust10", label="10y", kind=RATE_LIKE, quote="yield", stale_after_days=5)
    a_month_back = series.asof(series.index[-1] - pd.Timedelta(days=30))
    assert row.change_1m == pytest.approx(series.iloc[-1] - a_month_back)


def test_year_range_covers_the_trailing_year_only():
    old = pd.Series([99.0], index=pd.DatetimeIndex(["2020-01-02"]))
    recent = daily([5.0, 1.0, 3.0])
    row = board_row(pd.concat([old, recent]), key="vix", label="VIX", kind=RATE_LIKE, quote="yield", stale_after_days=5)
    assert row.low_1y == pytest.approx(1.0)
    assert row.high_1y == pytest.approx(5.0)


def test_row_carries_its_key_label_and_kind():
    row = board_row(daily([1.0, 2.0]), key="vix", label="VIX", kind=RATE_LIKE, quote="yield", stale_after_days=5)
    assert isinstance(row, BoardRow)
    assert (row.key, row.label, row.kind) == ("vix", "VIX", RATE_LIKE)


def test_as_of_is_the_series_last_date():
    row = board_row(daily([1.0, 2.0]), key="vix", label="VIX", kind=RATE_LIKE, quote="yield", stale_after_days=5)
    assert row.as_of == "2026-09-18"


def test_a_single_observation_has_no_change_but_still_has_a_level():
    row = board_row(daily([4.2]), key="ust10", label="10y", kind=RATE_LIKE, quote="yield", stale_after_days=5)
    assert row.level == 4.2
    assert row.change_1d is None
    assert row.change_1m is None


def test_an_empty_series_is_rejected_rather_than_rendered():
    with pytest.raises(ValueError):
        board_row(pd.Series(dtype=float), key="ust10", label="10y", kind=RATE_LIKE, quote="yield", stale_after_days=5)


def test_board_sections_come_back_in_configured_order():
    levels = {"spx": daily([1.0, 2.0]), "vix": daily([3.0, 4.0])}
    board = build_board(levels, sections=(("Equities", ("spx",)), ("Other", ("vix",))), spreads=())
    assert [section.title for section in board] == ["Equities", "Other"]
    assert [row.key for row in board[0].rows] == ["spx"]


def test_a_series_that_failed_to_load_is_skipped_rather_than_blanking_the_board():
    levels = {"spx": daily([1.0, 2.0])}
    board = build_board(levels, sections=(("Equities", ("spx", "missing")),), spreads=())
    assert [row.key for row in board[0].rows] == ["spx"]


def test_a_section_with_nothing_to_show_is_dropped():
    board = build_board({}, sections=(("Equities", ("spx",)),), spreads=())
    assert board == []


def test_a_spread_row_is_the_long_tenor_minus_the_short_one():
    levels = {"ust2": daily([3.50, 3.55]), "ust10": daily([4.00, 3.98])}
    board = build_board(
        levels,
        sections=(("Curve", ("ust2", "ust10")),),
        spreads=(("2s10s", "Curve", "ust2", "ust10"),),
    )
    spread = next(row for row in board[0].rows if row.key == "2s10s")
    assert spread.level == pytest.approx(3.98 - 3.55)
    assert spread.change_1d == pytest.approx((3.98 - 3.55) - (4.00 - 3.50))
    assert spread.kind == RATE_LIKE


def test_a_spread_lands_in_its_named_section_after_the_tenors():
    levels = {"ust2": daily([3.50, 3.55]), "ust10": daily([4.00, 3.98])}
    board = build_board(
        levels,
        sections=(("Curve", ("ust2", "ust10")),),
        spreads=(("2s10s", "Curve", "ust2", "ust10"),),
    )
    assert [row.key for row in board[0].rows] == ["ust2", "ust10", "2s10s"]


def test_a_spread_whose_legs_are_missing_is_skipped():
    levels = {"ust2": daily([3.50, 3.55])}
    board = build_board(
        levels,
        sections=(("Curve", ("ust2",)),),
        spreads=(("2s10s", "Curve", "ust2", "ust10"),),
    )
    assert [row.key for row in board[0].rows] == ["ust2"]


def test_spread_legs_align_on_shared_dates_and_never_forward_fill():
    ust2 = pd.Series([3.5, 3.6], index=pd.DatetimeIndex(["2026-09-15", "2026-09-17"]))
    ust10 = pd.Series([4.0, 4.1], index=pd.DatetimeIndex(["2026-09-15", "2026-09-16"]))
    board = build_board(
        {"ust2": ust2, "ust10": ust10},
        sections=(("Curve", ()),),
        spreads=(("2s10s", "Curve", "ust2", "ust10"),),
    )
    spread = board[0].rows[0]
    assert spread.as_of == "2026-09-15"
    assert spread.level == pytest.approx(0.5)


# --- staleness -------------------------------------------------------------
# The board sits numbers of different publication cadences in one grid at
# identical visual weight. A row that cannot be fresh must say so, or the
# board teaches a stale level as a current one.

def _row_ending(days_ago, tolerance):
    end = pd.Timestamp.today().normalize() - pd.Timedelta(days=days_ago)
    series = pd.Series([1.0, 2.0], index=pd.bdate_range(end=end, periods=2))
    return board_row(
        series, key="usd", label="Broad dollar", kind=PRICE_LIKE,
        quote="price", stale_after_days=tolerance,
    )


def test_a_row_within_its_publication_tolerance_is_not_stale():
    assert _row_ending(days_ago=2, tolerance=12).stale is False


def test_a_row_past_its_publication_tolerance_is_stale():
    assert _row_ending(days_ago=20, tolerance=12).stale is True


def test_tolerance_comes_from_the_series_not_a_single_global_gate():
    """usd and wti carry different observed lags; the board must respect both."""
    assert _row_ending(days_ago=9, tolerance=12).stale is False
    assert _row_ending(days_ago=9, tolerance=8).stale is True


def test_a_spread_takes_the_wider_tolerance_of_its_two_legs():
    slow = pd.Series([1.0, 2.0], index=pd.bdate_range(end="2026-09-18", periods=2))
    board = build_board(
        {"usd": slow, "ust10": slow},
        sections=(("Curve", ()),),
        spreads=(("probe", "Curve", "usd", "ust10"),),
    )
    # usd tolerates 12 days, ust10 tolerates 5; the spread cannot be fresher
    # than its slowest leg, so it must not be judged against the stricter gate.
    assert board[0].rows[0].stale_after_days == 12

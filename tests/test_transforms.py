import warnings

import numpy as np
import pandas as pd
import pytest

from brief.transforms import (
    PRICE_LIKE,
    RATE_LIKE,
    align,
    mean_abs_pairwise_corr,
    percentile_rank,
    rolling_corr,
    rolling_percentile,
    to_change,
)


def dates(n, start="2020-01-01"):
    return pd.bdate_range(start, periods=n)


def test_price_like_becomes_log_return():
    s = pd.Series([100.0, 110.0], index=dates(2))
    out = to_change(s, PRICE_LIKE)
    assert len(out) == 1
    assert out.iloc[0] == pytest.approx(np.log(1.1))


def test_price_like_drops_non_positive_prices_without_warning():
    s = pd.Series([50.0, -37.0, 20.0, 25.0], index=dates(4))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = to_change(s, PRICE_LIKE)
    assert len(out) == 1
    assert out.index[0] == dates(4)[3]


def test_rate_like_becomes_first_difference_in_native_units():
    s = pd.Series([4.00, 4.07], index=dates(2))
    out = to_change(s, RATE_LIKE)
    assert out.iloc[0] == pytest.approx(0.07)


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        to_change(pd.Series([1.0, 2.0], index=dates(2)), "percent")


def test_align_intersects_dates_and_never_fills():
    a = pd.Series([1.0, 2.0, 3.0], index=dates(3)).rename("a")
    b = pd.Series([1.0, 3.0], index=[dates(3)[0], dates(3)[2]]).rename("b")
    out = align(a, b)
    assert list(out.index) == [dates(3)[0], dates(3)[2]]
    assert out.shape == (2, 2)


def test_percentile_rank_is_zero_at_minimum_and_hundred_at_maximum():
    rising = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=dates(5))
    assert percentile_rank(rising) == pytest.approx(100.0)
    assert percentile_rank(rising.iloc[::-1]) == pytest.approx(0.0)


def test_percentile_rank_is_midpoint_in_the_middle():
    s = pd.Series([1.0, 2.0, 4.0, 5.0, 3.0], index=dates(5))
    assert percentile_rank(s) == pytest.approx(50.0)


def test_percentile_rank_honours_the_trailing_window():
    s = pd.Series([100.0, 1.0, 2.0, 3.0], index=dates(4))
    assert percentile_rank(s, window=3) == pytest.approx(100.0)
    assert percentile_rank(s) == pytest.approx(66.6666, abs=1e-3)


def test_percentile_rank_needs_two_points():
    assert np.isnan(percentile_rank(pd.Series([1.0], index=dates(1))))


def test_rolling_percentile_matches_scalar_percentile_rank():
    s = pd.Series([5.0, 1.0, 2.0, 4.0, 3.0], index=dates(5))
    rolled = rolling_percentile(s, window=3)
    assert rolled.iloc[-1] == pytest.approx(percentile_rank(s, window=3))
    assert len(rolled) == 3


def test_rolling_corr_of_identical_series_is_one():
    s = pd.Series(np.arange(10, dtype=float) % 4, index=dates(10))
    out = rolling_corr(s, s, window=5)
    assert out.iloc[-1] == pytest.approx(1.0)


def test_mean_abs_pairwise_corr_ignores_the_diagonal():
    rng = np.random.default_rng(0)
    base = pd.Series(rng.normal(size=60), index=dates(60))
    df = pd.DataFrame({"a": base, "b": -base, "c": base})
    out = mean_abs_pairwise_corr(df, window=30)
    assert out.iloc[-1] == pytest.approx(1.0)
    assert len(out) == 31


def test_rolling_corr_never_exceeds_one():
    s = pd.Series(np.arange(80, dtype=float) % 7, index=dates(80))
    out = rolling_corr(s, s * 3.0 + 1.0, window=30)
    assert out.max() <= 1.0
    assert out.min() >= -1.0


def test_mean_abs_pairwise_corr_stays_within_unit_interval():
    s = pd.Series(np.arange(80, dtype=float) % 7, index=dates(80))
    df = pd.DataFrame({"a": s, "b": s * 2.0, "c": -s})
    out = mean_abs_pairwise_corr(df, window=30)
    assert out.max() <= 1.0
    assert out.min() >= 0.0

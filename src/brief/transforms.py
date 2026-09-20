"""Pure numerical transforms. No I/O, no state, no fitted parameters."""

import numpy as np
import pandas as pd

PRICE_LIKE = "price"
RATE_LIKE = "rate"


def to_change(s: pd.Series, kind: str) -> pd.Series:
    """Convert a level series to its daily change.

    Price-like series become log returns; rate-like series become first
    differences in their native units (basis points for yields and spreads,
    vol points for VIX). Mixing the two silently changes every correlation.
    """
    s = s.dropna().sort_index()
    if kind == PRICE_LIKE:
        return np.log(s / s.shift(1)).dropna()
    if kind == RATE_LIKE:
        return s.diff().dropna()
    raise ValueError(f"unknown series kind: {kind!r}")


def align(*series: pd.Series) -> pd.DataFrame:
    """Inner-join series on date.

    Never forward-fills: a filled value injects a false zero change and drags
    correlations toward zero on every holiday and publication gap.
    """
    return pd.concat(series, axis=1, join="inner").dropna()


def percentile_rank(s: pd.Series, window: int | None = None) -> float:
    """Percentile rank (0-100) of the last value within its trailing window.

    Minimum scores 0, maximum scores 100. Ties take the average rank.
    """
    s = s.dropna()
    if window is not None:
        s = s.iloc[-window:]
    n = len(s)
    if n < 2:
        return float("nan")
    rank = s.rank(method="average").iloc[-1]
    return float((rank - 1) / (n - 1) * 100)


def rolling_percentile(s: pd.Series, window: int) -> pd.Series:
    """percentile_rank evaluated at every date over a trailing window."""
    s = s.dropna()
    rank = s.rolling(window).rank(method="average")
    return ((rank - 1) / (window - 1) * 100).dropna()


def rolling_corr(a: pd.Series, b: pd.Series, window: int) -> pd.Series:
    """Rolling Pearson correlation of two change series."""
    df = align(a.rename("a"), b.rename("b"))
    return df["a"].rolling(window).corr(df["b"]).dropna()


def mean_abs_pairwise_corr(df: pd.DataFrame, window: int) -> pd.Series:
    """Mean absolute pairwise correlation across every column pair.

    High means one macro factor is driving everything; low means the assets
    are telling unrelated stories.
    """
    n = df.shape[1]
    corr = df.rolling(window).corr()
    abs_sum = corr.abs().groupby(level=0).sum().sum(axis=1)
    complete = corr.notna().groupby(level=0).sum().sum(axis=1) == n * n
    out = (abs_sum - n) / (n * (n - 1))
    return out.where(complete).dropna()

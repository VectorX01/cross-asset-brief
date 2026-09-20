"""The levels board.

The board is reference, not analysis: what a number is, what it just did, and
where it sits in its trailing year. The range column is the one that teaches —
a level on its own says nothing about whether it is high or low, and the point
of seeing these every day is to learn their scale.

Lookbacks are by calendar date rather than by row, because these series have
holidays and publication gaps and "a month ago" should mean a month ago.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from brief.config import PERCENT_QUOTES, SERIES
from brief.transforms import RATE_LIKE, align

MONTH = pd.Timedelta(days=30)
YEAR = pd.Timedelta(days=365)


@dataclass(frozen=True)
class BoardRow:
    key: str
    label: str
    kind: str
    quote: str
    level: float
    # Absolute move in the row's own units, and the percent move where a
    # percent means anything. A yield going 4.00 -> 4.07 is +7bp, not
    # +1.75%, so rate-like rows carry None.
    change_1d: float | None
    change_1d_pct: float | None
    change_1m: float | None
    change_1m_pct: float | None
    low_1y: float
    high_1y: float
    as_of: str
    stale_after_days: int
    stale: bool


def _move(latest: float, earlier: float, quote: str) -> tuple[float, float | None]:
    """The absolute move, and the percent move where one is meaningful.

    Keyed on the quote rather than the kind: VIX is rate-like for the
    differencing maths but is quoted "-2.27 (-12.8%)", while a percent on a
    yield means nothing. Whether a percent belongs is a display question.
    """
    absolute = latest - earlier
    if quote in PERCENT_QUOTES and earlier != 0:
        return absolute, (latest / earlier - 1.0) * 100.0
    return absolute, None


def board_row(
    series: pd.Series, *, key: str, label: str, kind: str, quote: str, stale_after_days: int
) -> BoardRow:
    """One row of the board, or ValueError if there is nothing to show."""
    observed = series.dropna().sort_index()
    if observed.empty:
        raise ValueError(f"{key}: no observations")

    last_date = observed.index[-1]
    level = float(observed.iloc[-1])

    change_1d, change_1d_pct = (
        _move(level, float(observed.iloc[-2]), quote) if len(observed) > 1 else (None, None)
    )

    a_month_back = observed.asof(last_date - MONTH)
    change_1m, change_1m_pct = (
        (None, None) if pd.isna(a_month_back) else _move(level, float(a_month_back), quote)
    )

    trailing_year = observed[observed.index > last_date - YEAR]

    return BoardRow(
        key=key,
        label=label,
        kind=kind,
        quote=quote,
        level=level,
        change_1d=change_1d,
        change_1d_pct=change_1d_pct,
        change_1m=change_1m,
        change_1m_pct=change_1m_pct,
        low_1y=float(trailing_year.min()),
        high_1y=float(trailing_year.max()),
        as_of=str(last_date.date()),
        stale_after_days=stale_after_days,
        stale=(date.today() - last_date.date()) > timedelta(days=stale_after_days),
    )


@dataclass(frozen=True)
class BoardSection:
    title: str
    rows: tuple[BoardRow, ...]


def _spread_series(levels: dict[str, pd.Series], short_key: str, long_key: str) -> pd.Series | None:
    """Long tenor minus short, on shared dates only.

    Aligning rather than forward-filling matters here: the two legs publish
    on the same schedule in normal weeks, but a gap in one would otherwise
    invent a spread move out of a stale quote.
    """
    short, long_ = levels.get(short_key), levels.get(long_key)
    if short is None or long_ is None:
        return None
    joined = align(short.rename("short"), long_.rename("long"))
    if joined.empty:
        return None
    return joined["long"] - joined["short"]


def build_board(
    levels: dict[str, pd.Series],
    *,
    sections: tuple[tuple[str, tuple[str, ...]], ...],
    spreads: tuple[tuple[str, str, str, str], ...],
) -> list[BoardSection]:
    """Assemble the board. Anything that failed to load is left out, not faked."""
    rows: dict[str, list[BoardRow]] = {title: [] for title, _ in sections}

    for title, keys in sections:
        for key in keys:
            series, definition = levels.get(key), SERIES.get(key)
            if series is None or definition is None:
                continue
            try:
                rows[title].append(
                    board_row(
                        series,
                        key=key,
                        label=definition.label,
                        kind=definition.kind,
                        quote=definition.quote,
                        stale_after_days=definition.stale_after_days,
                    )
                )
            except ValueError:
                continue

    for label, title, short_key, long_key in spreads:
        if title not in rows:
            continue
        series = _spread_series(levels, short_key, long_key)
        if series is None:
            continue
        try:
            rows[title].append(board_row(
                    series,
                    key=label,
                    label=label,
                    kind=RATE_LIKE,
                    quote="bp",
                    # A spread cannot be fresher than its slowest leg.
                    stale_after_days=max(
                        SERIES[short_key].stale_after_days,
                        SERIES[long_key].stale_after_days,
                    ),
                ))
        except ValueError:
            continue

    return [
        BoardSection(title=title, rows=tuple(rows[title]))
        for title, _ in sections
        if rows[title]
    ]

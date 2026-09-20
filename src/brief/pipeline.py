"""Fetch, compute, assemble. Stateless: a missed run costs nothing."""

import math
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from brief.config import BOARD_SECTIONS, BOARD_SPREADS, SERIES, source_of
from brief.levels import build_board
from brief.metrics.registry import REGISTRY
from brief.sources.fred import fetch
from brief.transforms import percentile_rank

SPARK_POINTS = 120

# How old a CoT-backed tile's newest observation may be before it is marked
# stale. CoT is weekly and already three days old when published, so it gets a
# wide gate. FRED series carry their own tolerance on SeriesDef.
CFTC_STALE_AFTER_DAYS = 12


@dataclass
class Tile:
    name: str
    title: str
    value: float | None
    pctile: float | None
    sentence: str
    history: list[float]
    as_of: str
    unit: str
    context: str
    why: str
    implication: str
    sources: tuple[str, ...]
    error: str | None = None
    stale: bool = False


def load_levels() -> tuple[dict[str, pd.Series], dict[str, str]]:
    """Fetch everything. A failing source degrades the page, never blanks it."""
    from brief.config import CONTRACTS
    from brief.sources.cftc import fetch as fetch_cot

    levels: dict[str, pd.Series] = {}
    status: dict[str, str] = {}
    for key, definition in SERIES.items():
        try:
            levels[key] = fetch(definition.fred_id)
        except Exception as exc:
            status[f"FRED {definition.label} ({definition.fred_id})"] = str(exc)[:120]
    for key in CONTRACTS:
        try:
            levels[f"cot_{key}"] = fetch_cot(key)
        except Exception as exc:
            status[f"CFTC {CONTRACTS[key].label}"] = str(exc)[:120]
    return levels, status


def _sources_for(metric) -> tuple[str, ...]:
    return tuple(sorted({source_of(name) for name in metric.inputs}))


def _staleness_gate(metric) -> int:
    """The gate is the loosest tolerance among a metric's own inputs: a metric
    is only as fresh as its slowest-publishing input. CoT is weekly and
    already three days old when published, so any CFTC input gets the wide
    weekly gate; a FRED input carries its own series-specific tolerance
    (SeriesDef.stale_after_days), since publication lag is a property of the
    series, not of the metric that happens to consume it."""

    def tolerance(name: str) -> int:
        if source_of(name) == "CFTC":
            return CFTC_STALE_AFTER_DAYS
        return SERIES[name].stale_after_days

    return max(tolerance(name) for name in metric.inputs)


def _context_label(series: pd.Series, window: int | None) -> str:
    """What this tile's percentile is a percentile *of*.

    Derived from the data actually loaded, never hardcoded: "18th percentile"
    alone is the abstraction the design set out to avoid, since the 18th
    percentile of one year and of forty are different claims and the reader
    cannot tell them apart. A window wider than the history available reports
    the history that is actually there.
    """
    # dropna first, exactly as percentile_rank does, so the window stated
    # here is the window the percentile was actually taken over.
    series = series.dropna()
    if window is None or window >= len(series):
        return f"since {series.index[0].year}"
    span = series.index[-1] - series.index[-window]
    years = span.days / 365.25
    if years >= 1:
        return f"of the last {round(years)} years"
    return f"of the last {round(span.days / 30.44)} months"


def _unavailable(metric, reason: str) -> Tile:
    """A tile that says why it has no number, rather than rendering blank."""
    return Tile(
        name=metric.name,
        title=metric.title,
        value=None,
        pctile=None,
        sentence=f"unavailable — {reason}",
        history=[],
        as_of="",
        unit=metric.unit,
        why=metric.why,
        implication=metric.implication,
        context="",
        sources=_sources_for(metric),
        error=reason,
    )


def _tile_for(metric, levels: dict[str, pd.Series]) -> Tile:
    missing = [name for name in metric.inputs if name not in levels]
    if missing:
        return _unavailable(metric, f"missing input {', '.join(missing)}")
    # Everything that touches the computed series stays inside this block.
    # An empty series raises IndexError on .iloc[-1], and a series too short
    # to rank yields a NaN percentile that would reach ordinal() and raise at
    # render time -- both of which are exactly the "broken metric" the except
    # clause exists to contain. A short series is not hypothetical: FRED has
    # truncated this project's series twice (see config.py).
    try:
        series = metric.fn({name: levels[name] for name in metric.inputs})
        value = float(series.iloc[-1])
        pctile = percentile_rank(series, window=metric.context_window)
        if pctile is None or math.isnan(pctile):
            # Percentile is the page's only vocabulary. A tile that cannot
            # produce one has nothing to say, so it says so.
            return _unavailable(metric, "not enough history for a percentile")
        last = series.index[-1].date()
        stale = (date.today() - last) > timedelta(days=_staleness_gate(metric))
        return Tile(
            name=metric.name,
            title=metric.title,
            value=value,
            pctile=pctile,
            sentence=metric.interpret(value, pctile),
            history=[float(v) for v in series.iloc[-SPARK_POINTS:]],
            as_of=str(last),
            unit=metric.unit,
        why=metric.why,
        implication=metric.implication,
            context=_context_label(series, metric.context_window),
            sources=_sources_for(metric),
            stale=stale,
        )
    except Exception as exc:  # a broken metric must not take the page down
        return _unavailable(metric, str(exc))


def build_payload(levels: dict[str, pd.Series], source_status: dict[str, str] | None = None) -> dict:
    # Imported locally, not at module level: rank.py imports Tile from this
    # module, so a top-level import here would reintroduce that cycle.
    from brief.rank import rank_anomalies

    # The metric declares its own role; the pipeline never knows which metric
    # it is looking at. Branching on t.name == "divergence" here meant a
    # rename would have made the Setup block silently vanish.
    tiles, setup = [], None
    for metric in REGISTRY.values():
        tile = _tile_for(metric, levels)
        tiles.append(tile)
        if metric.role == "setup" and tile.error is None:
            setup = tile
    return {
        "date": str(date.today()),
        "tiles": tiles,
        "unusual": rank_anomalies(tiles),
        "setup": setup,
        "board": build_board(levels, sections=BOARD_SECTIONS, spreads=BOARD_SPREADS),
        "source_status": source_status or {},
    }

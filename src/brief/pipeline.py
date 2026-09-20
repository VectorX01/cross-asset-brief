"""Fetch, compute, assemble. Stateless: a missed run costs nothing."""

import math
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from brief.config import SERIES, source_of
from brief.metrics.registry import REGISTRY
from brief.sources.fred import fetch
from brief.transforms import percentile_rank

SPARK_POINTS = 120

# How old a metric's newest observation may be before the tile is marked stale.
# CoT is weekly and already three days old when published, so it gets a wide gate.
STALE_AFTER_DAYS = {"daily": 5, "weekly": 12}


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
            status[f"fred:{definition.fred_id}"] = str(exc)[:120]
    for key in CONTRACTS:
        try:
            levels[f"cot_{key}"] = fetch_cot(key)
        except Exception as exc:
            status[f"cftc:{key}"] = str(exc)[:120]
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
            return STALE_AFTER_DAYS["weekly"]
        return SERIES[name].stale_after_days

    return max(tolerance(name) for name in metric.inputs)


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
            sources=_sources_for(metric),
            stale=stale,
        )
    except Exception as exc:  # a broken metric must not take the page down
        return _unavailable(metric, str(exc))


def build_payload(levels: dict[str, pd.Series], source_status: dict[str, str] | None = None) -> dict:
    # Imported locally, not at module level: rank.py imports Tile from this
    # module, so a top-level import here would reintroduce that cycle.
    from brief.rank import rank_anomalies

    tiles = [_tile_for(metric, levels) for metric in REGISTRY.values()]
    setup = next((t for t in tiles if t.name == "divergence" and t.error is None), None)
    return {
        "date": str(date.today()),
        "tiles": tiles,
        "unusual": rank_anomalies(tiles),
        "setup": setup,
        "source_status": source_status or {},
    }

"""Fetch, compute, assemble. Stateless: a missed run costs nothing."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from brief.config import SERIES
from brief.metrics.registry import REGISTRY
from brief.sources.fred import fetch
from brief.transforms import percentile_rank

SPARK_POINTS = 120


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
    error: str | None = None
    stale: bool = False


def load_levels() -> dict[str, pd.Series]:
    """Fetch every configured series' full history."""
    return {key: fetch(definition.fred_id) for key, definition in SERIES.items()}


def _tile_for(metric, levels: dict[str, pd.Series]) -> Tile:
    missing = [name for name in metric.inputs if name not in levels]
    if missing:
        return Tile(
            name=metric.name,
            title=metric.title,
            value=None,
            pctile=None,
            sentence=f"unavailable — missing input {', '.join(missing)}",
            history=[],
            as_of="",
            unit=metric.unit,
            error=f"missing input {', '.join(missing)}",
        )
    try:
        series = metric.fn({name: levels[name] for name in metric.inputs})
    except Exception as exc:  # a broken metric must not take the page down
        return Tile(
            name=metric.name,
            title=metric.title,
            value=None,
            pctile=None,
            sentence=f"unavailable — {exc}",
            history=[],
            as_of="",
            unit=metric.unit,
            error=str(exc),
        )
    value = float(series.iloc[-1])
    if metric.unit == "corr":
        # Pearson correlation is bounded to [-1, 1] by definition; pandas'
        # rolling implementation can overshoot that by float epsilon
        # (observed ~1e-15 on perfectly proportional inputs). Clip the
        # displayed value rather than let a bounded statistic read as
        # unbounded — this corrects floating-point noise, not the metric.
        value = max(-1.0, min(1.0, value))
    pctile = percentile_rank(series, window=metric.context_window)
    return Tile(
        name=metric.name,
        title=metric.title,
        value=value,
        pctile=pctile,
        sentence=metric.interpret(value, pctile),
        history=[float(v) for v in series.iloc[-SPARK_POINTS:]],
        as_of=str(series.index[-1].date()),
        unit=metric.unit,
    )


def build_payload(levels: dict[str, pd.Series]) -> dict:
    tiles = [_tile_for(metric, levels) for metric in REGISTRY.values()]
    return {"date": str(date.today()), "tiles": tiles}

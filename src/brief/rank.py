"""The anomaly ranker.

Ranking heterogeneous metrics against each other is only legitimate because
every metric speaks the same language: a percentile. Distance from the 50th
is genuinely comparable across tiles in a way that |z| would not be.
"""

import math

from brief.pipeline import Tile


def rank_anomalies(tiles: list[Tile], top: int = 5) -> list[Tile]:
    # NaN must be excluded explicitly, not just None: every comparison
    # against NaN is False, so a NaN percentile does not sort to an end --
    # it scrambles the order of the tiles around it.
    usable = [
        t
        for t in tiles
        if t.error is None and t.pctile is not None and not math.isnan(t.pctile)
    ]
    return sorted(usable, key=lambda t: abs(t.pctile - 50.0), reverse=True)[:top]

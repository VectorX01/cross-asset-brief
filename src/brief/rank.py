"""The anomaly ranker.

Ranking heterogeneous metrics against each other is only legitimate because
every metric speaks the same language: a percentile. Distance from the 50th
is genuinely comparable across tiles in a way that |z| would not be.
"""

from brief.pipeline import Tile


def rank_anomalies(tiles: list[Tile], top: int = 5) -> list[Tile]:
    usable = [t for t in tiles if t.error is None and t.pctile is not None]
    return sorted(usable, key=lambda t: abs(t.pctile - 50.0), reverse=True)[:top]

from brief.pipeline import Tile
from brief.rank import rank_anomalies


def tile(name, pctile, error=None):
    return Tile(
        name=name,
        title=name,
        value=0.0 if error is None else None,
        pctile=pctile,
        sentence=name,
        history=[],
        as_of="2026-09-20",
        unit="",
        sources=("FRED",),
        error=error,
    )


def test_ranks_by_distance_from_the_median():
    ranked = rank_anomalies([tile("a", 50.0), tile("b", 97.0), tile("c", 2.0)])
    assert [t.name for t in ranked] == ["c", "b", "a"]


def test_treats_both_tails_as_equally_unusual():
    ranked = rank_anomalies([tile("high", 95.0), tile("low", 5.0)])
    assert {t.name for t in ranked} == {"high", "low"}


def test_excludes_unavailable_tiles():
    ranked = rank_anomalies([tile("broken", None, error="boom"), tile("ok", 80.0)])
    assert [t.name for t in ranked] == ["ok"]


def test_returns_at_most_the_requested_count():
    tiles = [tile(str(i), float(i)) for i in range(20)]
    assert len(rank_anomalies(tiles, top=5)) == 5


def test_empty_input_is_not_an_error():
    assert rank_anomalies([]) == []

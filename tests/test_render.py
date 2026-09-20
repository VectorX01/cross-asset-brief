import numpy as np
import pandas as pd

from brief.metrics import cross_asset  # noqa: F401
from brief.metrics.registry import REGISTRY, Metric
from brief.pipeline import STALE_AFTER_DAYS, Tile, _staleness_gate, _tile_for, build_payload
from brief.render.page import render
from brief.render.svg import percentile_strip, sparkline


def _metric(inputs):
    return Metric(
        name="probe", title="Probe", inputs=inputs, context_window=None,
        fn=lambda levels: None, interpret=lambda value, pctile: "", unit="",
    )


def tile_named(payload, name):
    return next(t for t in payload["tiles"] if t.name == name)


def synthetic_levels(n=400):
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(7)
    shock = rng.normal(size=n)
    return {
        "equity": pd.Series(100 * np.exp(np.cumsum(shock * 0.01)), index=idx),
        "ust10": pd.Series(4.0 + np.cumsum(shock * 0.02), index=idx),
    }


def test_percentile_strip_places_the_mark_proportionally():
    left = percentile_strip(0.0)
    right = percentile_strip(100.0)
    assert left.startswith("<svg") and right.startswith("<svg")
    assert 'x1="0"' in left
    assert 'x1="160"' in right


def test_sparkline_emits_one_point_per_value():
    out = sparkline([1.0, 2.0, 3.0])
    assert out.count(",") == 3


def test_sparkline_survives_a_flat_series():
    out = sparkline([2.0, 2.0, 2.0])
    assert "<svg" in out
    assert "nan" not in out.lower()


def test_payload_has_one_tile_per_registered_metric():
    payload = build_payload(synthetic_levels())
    assert len(payload["tiles"]) == len(REGISTRY)
    tile = tile_named(payload, "stock_bond")
    assert -1.0 <= tile.value <= 1.0
    assert 0.0 <= tile.pctile <= 100.0
    assert tile.sentence
    assert tile.error is None


def test_payload_records_an_error_instead_of_raising_on_missing_input():
    payload = build_payload({"equity": synthetic_levels()["equity"]})
    tile = tile_named(payload, "stock_bond")
    assert tile.value is None
    assert "ust10" in tile.error


def test_render_produces_a_page_containing_the_sentence():
    payload = build_payload(synthetic_levels())
    html = render(payload)
    assert html.startswith("<!doctype html>")
    assert tile_named(payload, "stock_bond").sentence in html
    assert "viewport" in html


def test_render_shows_the_unavailable_reason_rather_than_a_blank():
    payload = build_payload({"equity": synthetic_levels()["equity"]})
    html = render(payload)
    assert "unavailable" in html


def test_tile_for_catches_a_metric_that_raises_mid_computation():
    def boom(levels):
        raise ValueError("metric exploded")

    metric = Metric(
        name="boom", title="Boom", inputs=("equity",), context_window=None,
        fn=boom, interpret=lambda value, pctile: "never reached", unit="",
    )
    tile = _tile_for(metric, synthetic_levels())
    assert tile.value is None
    assert "metric exploded" in tile.error


def test_payload_tile_reports_its_source():
    payload = build_payload(synthetic_levels())
    tile = tile_named(payload, "stock_bond")
    assert tile.sources == ("FRED",)
    html = render(payload)
    assert "FRED" in html


def test_a_tile_older_than_its_cadence_is_marked_stale():
    levels = synthetic_levels()  # ends in 2021, far past any cadence
    payload = build_payload(levels)
    assert tile_named(payload, "stock_bond").stale is True
    assert "stale" in render(payload)


def test_staleness_gate_for_default_tolerance_fred_inputs_is_five_days():
    assert _staleness_gate(_metric(("equity", "ust10"))) == 5


def test_staleness_gate_widens_for_a_slower_publishing_fred_input():
    # "usd" -> DTWEXBGS, pinned to a 12-day tolerance for its observed lag.
    assert _staleness_gate(_metric(("equity", "usd"))) == 12


def test_staleness_gate_widens_for_any_cftc_input():
    assert _staleness_gate(_metric(("cot_es",))) == STALE_AFTER_DAYS["weekly"]
    assert _staleness_gate(_metric(("cot_es", "spx"))) == STALE_AFTER_DAYS["weekly"]


def test_a_genuinely_ancient_tile_is_still_marked_stale_even_with_a_wide_gate():
    # Widening individual gates must not disable the feature outright: a
    # metric whose only input is the slowest FRED series (usd, 12-day gate)
    # is still marked stale once its data is far older than even that.
    old_levels = synthetic_levels()  # ends in 2021
    old_levels["usd"] = old_levels["equity"].rename("usd")
    metric = _metric(("usd",))
    assert _staleness_gate(metric) == 12
    tile = _tile_for(
        Metric(
            name="usd_only", title="USD only", inputs=("usd",), context_window=None,
            fn=lambda levels: levels["usd"],
            interpret=lambda value, pctile: "n/a", unit="",
        ),
        old_levels,
    )
    assert tile.stale is True


def test_source_failures_appear_in_the_header():
    payload = build_payload(synthetic_levels(), source_status={"cftc": "HTTP 503"})
    html = render(payload)
    assert "cftc" in html
    assert "503" in html


def test_unusual_and_setup_sections_render_with_a_correctly_suffixed_ordinal():
    tile = Tile(
        name="stock_bond", title="Stock/bond", value=0.5, pctile=72.0,
        sentence="an unusual reading", history=[1.0, 2.0], as_of="2021-01-01",
        unit="", sources=("FRED",),
    )
    payload = {
        "date": "2021-01-01",
        "tiles": [tile],
        "unusual": [tile],
        "setup": tile,
        "source_status": {},
    }
    html = render(payload)
    assert "What's unusual today" in html
    assert "Setup" in html
    assert "72nd" in html
    assert "72th" not in html

import numpy as np
import pandas as pd

from brief.metrics import cross_asset  # noqa: F401
from brief.metrics.registry import REGISTRY, Metric
from brief.pipeline import STALE_AFTER_DAYS, Tile, _staleness_gate, _tile_for, build_payload
from brief.render.page import format_value, render
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
        unit="", context="since 1971", sources=("FRED",),
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


def test_load_levels_keeps_going_when_one_source_fails(monkeypatch):
    import brief.pipeline as pipeline

    def fake_fred(series_id, api_key=None):
        if series_id == "VIXCLS":
            raise RuntimeError("HTTP 503")
        return pd.Series([1.0, 2.0], index=pd.bdate_range("2026-01-01", periods=2))

    def fake_cot(contract_key):
        return pd.Series([1.0, 2.0], index=pd.bdate_range("2026-01-01", periods=2))

    monkeypatch.setattr(pipeline, "fetch", fake_fred)
    monkeypatch.setattr("brief.sources.cftc.fetch", fake_cot)

    levels, status = pipeline.load_levels()

    assert "vix" not in levels
    assert "equity" in levels and "ust10" in levels
    assert any("VIXCLS" in key or "vix" in key for key in status)
    assert any("503" in message for message in status.values())


def test_a_stale_setup_tile_is_marked_stale_in_its_own_section():
    stale_tile = Tile(
        name="divergence", title="Positioning-price divergence", value=5.0, pctile=90.0,
        sentence="setup sentence", history=[1.0, 2.0], as_of="2020-01-01",
        unit="pctile pts", context="since 2006", sources=("CFTC", "FRED"), stale=True,
    )
    payload = {
        "date": "2020-01-01",
        "tiles": [stale_tile],
        "unusual": [],
        "setup": stale_tile,
        "source_status": {},
    }
    html = render(payload)
    setup_section = html.split("<h2>Setup</h2>")[1].split("<h2>Metrics</h2>")[0]
    assert 'class="asof stale"' in setup_section
    assert "CFTC" in setup_section and "FRED" in setup_section


def test_tile_for_survives_a_metric_that_returns_an_empty_series():
    # FRED has truncated this project's series twice already; a metric whose
    # window outruns the history it was given must degrade to one unavailable
    # tile, not take the whole page down.
    metric = Metric(
        name="empty", title="Empty", inputs=("equity",), context_window=None,
        fn=lambda levels: pd.Series(dtype=float, index=pd.DatetimeIndex([])),
        interpret=lambda value, pctile: "never reached", unit="",
    )
    tile = _tile_for(metric, synthetic_levels())
    assert tile.value is None
    assert tile.error


def test_tile_for_marks_a_series_too_short_to_rank_unavailable():
    # percentile_rank returns NaN for n < 2. Percentile is the page's only
    # vocabulary, so a tile that cannot produce one has nothing to say -- and
    # a NaN must never reach ordinal(), which raises on it.
    idx = pd.bdate_range("2026-09-01", periods=1)
    metric = Metric(
        name="one_point", title="One point", inputs=("equity",), context_window=None,
        fn=lambda levels: pd.Series([1.0], index=idx),
        interpret=lambda value, pctile: "never reached", unit="",
    )
    tile = _tile_for(metric, synthetic_levels())
    assert tile.value is None
    assert tile.pctile is None
    assert "percentile" in tile.error


def test_a_full_history_tile_states_the_year_its_context_starts():
    # "18th percentile" is the abstraction the spec set out to avoid: the 18th
    # percentile of one year and of forty are different claims. The window is
    # derived from the data actually loaded, never hardcoded.
    tile = _tile_for(REGISTRY["stock_bond"], synthetic_levels())
    assert tile.context == "since 2020"
    assert tile.context in render(build_payload(synthetic_levels()))


def test_a_windowed_tile_states_its_window_not_its_start_year():
    weekly = pd.date_range("2016-01-05", periods=400, freq="W-TUE")
    metric = Metric(
        name="windowed", title="Windowed", inputs=("equity",), context_window=156,
        fn=lambda levels: pd.Series(np.arange(400, dtype=float), index=weekly),
        interpret=lambda value, pctile: "n/a", unit="",
    )
    tile = _tile_for(metric, synthetic_levels())
    assert tile.context == "of the last 3 years"


def test_a_window_longer_than_the_history_reports_the_history_it_has():
    # Claiming a three-year window over eighteen months of data would be the
    # hardcoded-prose bug in another form.
    weekly = pd.date_range("2025-01-07", periods=80, freq="W-TUE")
    metric = Metric(
        name="short_history", title="Short", inputs=("equity",), context_window=156,
        fn=lambda levels: pd.Series(np.arange(80, dtype=float), index=weekly),
        interpret=lambda value, pctile: "n/a", unit="",
    )
    assert _tile_for(metric, synthetic_levels()).context == "since 2025"


def _tile(**overrides):
    fields = dict(
        name="t", title="T", value=1.0, pctile=50.0, sentence="s",
        history=[1.0, 2.0], as_of="2026-09-20", unit="", context="since 2020",
        sources=("FRED",),
    )
    fields.update(overrides)
    return Tile(**fields)


def test_headline_values_are_formatted_by_their_unit():
    # Every tile used "%+.2f" regardless of unit, so five of nine showed a
    # headline like -1868126.00: no separator, two meaningless decimals, no
    # unit -- directly above prose that formatted the same number correctly.
    assert format_value(0.41, "corr") == "+0.41"
    assert format_value(-0.41, "corr") == "-0.41"
    assert format_value(5.4, "pctile pts") == "+5 pctile pts"
    assert format_value(-1868126.0, "contracts") == "-1,868,126 contracts"
    assert format_value(133116.0, "contracts") == "+133,116 contracts"


def test_an_unknown_unit_still_renders_a_number():
    assert format_value(1.5, "furlongs") == "+1.50"


def test_a_positioning_headline_renders_with_separators_not_raw_float():
    tile = _tile(name="pos_es", value=-1868126.0, unit="contracts")
    payload = {
        "date": "2026-09-20", "tiles": [tile], "unusual": [], "setup": None,
        "source_status": {},
    }
    html = render(payload)
    assert "-1,868,126 contracts" in html
    assert "-1868126.00" not in html


def test_the_setup_headline_is_formatted_by_unit_too():
    tile = _tile(name="divergence", value=37.4, unit="pctile pts")
    payload = {
        "date": "2026-09-20", "tiles": [tile], "unusual": [], "setup": tile,
        "source_status": {},
    }
    assert "+37 pctile pts" in render(payload)

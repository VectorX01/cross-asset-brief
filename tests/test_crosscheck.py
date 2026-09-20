"""Cross-source reconciliation.

An unofficial source is defensible only if it is checked. Where two providers
carry the same thing, compare them and say so on the page rather than quietly
trusting one.
"""

import pandas as pd
import pytest

from brief.crosscheck import CheckResult, run_checks


def series(values, dates):
    return pd.Series([float(v) for v in values], index=pd.DatetimeIndex(dates))


PAIR = {"spx": ("S&P 500", ("FRED", "SP500"), 0.1)}


def fetcher(mapping):
    def fetch(source, series_id):
        return mapping[(source, series_id)]

    return fetch


def test_two_sources_that_agree_pass():
    levels = {"spx": series([100.0, 101.0], ["2026-09-17", "2026-09-18"])}
    partner = series([100.0, 101.02], ["2026-09-17", "2026-09-18"])
    result = run_checks(levels, PAIR, fetcher({("FRED", "SP500"): partner}))[0]
    assert result.ok is True
    assert result.diff_pct == pytest.approx(0.0198, abs=1e-3)


def test_two_sources_that_disagree_beyond_tolerance_fail():
    levels = {"spx": series([100.0, 101.0], ["2026-09-17", "2026-09-18"])}
    partner = series([100.0, 105.0], ["2026-09-17", "2026-09-18"])
    result = run_checks(levels, PAIR, fetcher({("FRED", "SP500"): partner}))[0]
    assert result.ok is False
    # |101 - 105| / 105: the reference source is the denominator.
    assert result.diff_pct == pytest.approx(3.81, abs=0.01)


def test_the_comparison_uses_the_latest_shared_date_not_each_series_own_last():
    """The whole point. FRED's crude ran three days behind Yahoo's during a
    week crude moved ten percent; comparing each source's own last value would
    have reported a divergence that was purely staleness."""
    fresh = series([100.0, 96.0], ["2026-09-15", "2026-09-18"])
    stale = series([100.05], ["2026-09-15"])
    result = run_checks({"spx": fresh}, PAIR, fetcher({("FRED", "SP500"): stale}))[0]
    assert result.as_of == "2026-09-15"
    assert result.ok is True


def test_a_pair_with_no_shared_date_is_reported_rather_than_silently_skipped():
    a = series([100.0], ["2026-09-18"])
    b = series([100.0], ["2026-01-02"])
    result = run_checks({"spx": a}, PAIR, fetcher({("FRED", "SP500"): b}))[0]
    assert result.ok is False
    assert "no shared" in result.note


def test_a_partner_that_fails_to_fetch_is_reported_not_raised():
    def boom(source, series_id):
        raise RuntimeError("HTTP 503")

    result = run_checks({"spx": series([1.0], ["2026-09-18"])}, PAIR, boom)[0]
    assert result.ok is False
    assert "503" in result.note


def test_a_series_absent_from_levels_produces_no_check():
    assert run_checks({}, PAIR, fetcher({})) == []


def test_results_carry_the_label_a_reader_would_recognise():
    levels = {"spx": series([100.0], ["2026-09-18"])}
    partner = series([100.0], ["2026-09-18"])
    result = run_checks(levels, PAIR, fetcher({("FRED", "SP500"): partner}))[0]
    assert isinstance(result, CheckResult)
    assert result.label == "S&P 500"

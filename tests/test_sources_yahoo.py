"""Yahoo's chart endpoint: prices FRED either lags badly or does not carry.

Used through plain `requests` rather than yfinance — the payload is simple
enough that a dependency would add a breakage layer without adding anything.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from brief.sources.yahoo import YahooError, fetch, parse_chart

FIXTURE = Path(__file__).parent / "fixtures" / "yahoo_gold.json"


def payload():
    return json.loads(FIXTURE.read_text())


def test_parse_returns_a_sorted_float_series_indexed_by_date():
    series = parse_chart(payload())
    assert isinstance(series, pd.Series)
    assert series.dtype == float
    assert isinstance(series.index, pd.DatetimeIndex)
    assert series.index.is_monotonic_increasing


def test_a_session_with_no_close_is_dropped_rather_than_carried_forward():
    raw = payload()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
    assert None in raw, "fixture must contain a null close"
    series = parse_chart(payload())
    assert len(series) == len(raw) - raw.count(None)
    assert not series.isna().any()


def test_the_index_is_a_calendar_date_not_an_exchange_timestamp():
    """Yahoo returns epoch seconds at session open in exchange-local time;
    the board joins on dates, so a stray time component would never align."""
    series = parse_chart(payload())
    assert (series.index.normalize() == series.index).all()


def test_a_payload_carrying_an_error_is_rejected():
    with pytest.raises(YahooError, match="No data found"):
        parse_chart({"chart": {"result": None, "error": {"description": "No data found"}}})


def test_a_payload_with_no_result_is_rejected():
    with pytest.raises(YahooError):
        parse_chart({"chart": {"result": [], "error": None}})


def test_a_result_with_no_timestamps_is_rejected_rather_than_returning_empty():
    with pytest.raises(YahooError):
        parse_chart(
            {
                "chart": {
                    "result": [
                        {
                            "meta": {"symbol": "X"},
                            "timestamp": [],
                            "indicators": {"quote": [{"close": []}]},
                        }
                    ],
                    "error": None,
                }
            }
        )


def test_fetch_sends_a_user_agent_because_yahoo_refuses_requests_without_one(monkeypatch):
    seen = {}

    class Response:
        status_code = 200

        def json(self):
            return payload()

    def fake_get(url, params=None, headers=None, timeout=None):
        seen["headers"] = headers or {}
        return Response()

    monkeypatch.setattr("brief.sources.yahoo.requests.get", fake_get)
    fetch("GC=F")
    assert "User-Agent" in seen["headers"]


def test_fetch_wraps_a_transport_failure_without_leaking_the_url(monkeypatch):
    import requests

    def fake_get(url, params=None, headers=None, timeout=None):
        raise requests.ConnectionError("failed to reach https://query1.finance.yahoo.com/v8/x")

    monkeypatch.setattr("brief.sources.yahoo.requests.get", fake_get)
    with pytest.raises(YahooError) as caught:
        fetch("GC=F")
    assert "query1.finance.yahoo.com" not in str(caught.value)
    assert "GC=F" in str(caught.value)

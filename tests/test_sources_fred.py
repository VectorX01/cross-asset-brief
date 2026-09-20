import json
from pathlib import Path

import pandas as pd
import pytest

from brief.sources.fred import FredError, fetch, parse_observations

FIXTURE = Path(__file__).parent / "fixtures" / "fred_dgs10.json"


def test_parse_returns_a_sorted_float_series():
    payload = json.loads(FIXTURE.read_text())
    s = parse_observations(payload)
    assert isinstance(s, pd.Series)
    assert s.dtype == float
    assert isinstance(s.index, pd.DatetimeIndex)
    assert s.index.is_monotonic_increasing


def test_parse_drops_fred_missing_value_marker():
    payload = json.loads(FIXTURE.read_text())
    raw = payload["observations"]
    assert any(o["value"] == "." for o in raw), "fixture must contain a holiday"
    s = parse_observations(payload)
    assert len(s) < len(raw)
    assert not s.isna().any()


def test_parse_rejects_a_payload_with_no_observations_key():
    with pytest.raises(FredError):
        parse_observations({"error_message": "Bad Request."})


def test_fetch_requires_an_api_key(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(FredError, match="FRED_API_KEY"):
        fetch("DGS10")


def test_a_transport_failure_never_carries_the_api_key(monkeypatch):
    # requests' exceptions embed the full query string, api_key included, and
    # load_levels puts that string straight into a public page and a public
    # CI log. Only a str(exc)[:120] truncation stood between the key and both.
    import requests

    import brief.sources.fred as fred

    leaky = requests.ConnectionError(
        "HTTPSConnectionPool(host='api.stlouisfed.org', port=443): Max retries "
        "exceeded with url: /fred/series/observations?series_id=DGS10&"
        "api_key=abcdef0123456789abcdef0123456789&file_type=json "
        "(Caused by NewConnectionError('failed to establish a new connection'))"
    )

    def boom(*args, **kwargs):
        raise leaky

    monkeypatch.setenv("FRED_API_KEY", "abcdef0123456789abcdef0123456789")
    monkeypatch.setattr(fred.requests, "get", boom)
    with pytest.raises(FredError) as excinfo:
        fred.fetch("DGS10")

    message = str(excinfo.value)
    assert "api_key" not in message
    assert "abcdef0123456789abcdef0123456789" not in message
    assert "stlouisfed.org" not in message
    assert "DGS10" in message and "ConnectionError" in message

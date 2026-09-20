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

import json
from pathlib import Path

import pandas as pd
import pytest

from brief.sources.cftc import CftcError, parse_positions

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_tff_returns_net_positions_sorted_by_date():
    rows = json.loads((FIXTURES / "cftc_tff.json").read_text())
    s = parse_positions(rows, "tff")
    assert isinstance(s, pd.Series)
    assert s.index.is_monotonic_increasing
    assert s.dtype == float


def test_parse_disagg_returns_net_positions():
    rows = json.loads((FIXTURES / "cftc_disagg.json").read_text())
    s = parse_positions(rows, "disagg")
    assert len(s) > 0
    assert s.dtype == float


def test_net_position_is_long_minus_short():
    rows = json.loads((FIXTURES / "cftc_tff.json").read_text())
    s = parse_positions(rows, "tff")
    row = rows[0]
    from brief.sources.cftc import FIELDS

    date_field = "report_date_as_yyyy_mm_dd"
    long_field, short_field = FIELDS["tff"]
    expected = float(row[long_field]) - float(row[short_field])
    assert s.loc[pd.Timestamp(row[date_field][:10])] == pytest.approx(expected)


def test_parse_rejects_an_unknown_report():
    with pytest.raises(CftcError):
        parse_positions([], "legacy")


def test_parse_rejects_empty_rows():
    with pytest.raises(CftcError, match="no rows"):
        parse_positions([], "tff")

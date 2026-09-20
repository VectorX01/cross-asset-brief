import json
from pathlib import Path

import pandas as pd
import pytest

from brief.sources.cftc import FIELDS, CftcError, parse_positions, splice

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


def test_splice_concatenates_disjoint_series_with_no_duplicates():
    # The fixture is a single market ordered by report date DESC, so the
    # first half is disjoint in date from the second half — the same shape
    # as splicing a contract's pre- and post-rename market codes.
    rows = json.loads((FIXTURES / "cftc_tff.json").read_text())
    recent = parse_positions(rows[:10], "tff")
    older = parse_positions(rows[10:], "tff")
    combined = splice([older, recent])
    assert len(combined) == len(rows)
    assert combined.index.is_monotonic_increasing
    assert not combined.index.has_duplicates


def test_splice_rejects_overlapping_dates():
    rows = json.loads((FIXTURES / "cftc_tff.json").read_text())
    a = parse_positions(rows, "tff")
    b = parse_positions(rows, "tff")  # same dates as `a` -> overlap
    with pytest.raises(CftcError, match="overlapping"):
        splice([a, b])


def test_parse_skips_rows_missing_the_position_fields():
    rows = json.loads((FIXTURES / "cftc_tff.json").read_text())
    incomplete = dict(rows[0])
    long_field, short_field = FIELDS["tff"]
    del incomplete[long_field]
    s = parse_positions([incomplete, *rows[1:]], "tff")
    assert len(s) == len(rows) - 1


def test_parse_raises_when_no_row_carries_the_position_fields():
    rows = json.loads((FIXTURES / "cftc_tff.json").read_text())
    stripped = [
        {k: v for k, v in row.items() if k not in FIELDS["tff"]} for row in rows
    ]
    with pytest.raises(CftcError):
        parse_positions(stripped, "tff")

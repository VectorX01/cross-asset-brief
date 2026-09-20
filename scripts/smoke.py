"""Manual live check. Run: .venv/bin/python scripts/smoke.py"""

from brief.config import CONTRACTS, SERIES
from brief.sources.cftc import fetch as fetch_cot
from brief.sources.fred import fetch

for key, definition in SERIES.items():
    series = fetch(definition.series_id)
    print(f"{key:8} {definition.series_id:16} {len(series):>6} obs  {series.index[0].date()} -> {series.index[-1].date()}")

for key in CONTRACTS:
    series = fetch_cot(key)
    print(f"{key:8} {len(series):>6} reports  {series.index[0].date()} -> {series.index[-1].date()}")

"""Manual live check. Run: .venv/bin/python scripts/smoke.py"""

from brief.config import SERIES
from brief.sources.fred import fetch

for key, definition in SERIES.items():
    series = fetch(definition.fred_id)
    print(f"{key:8} {definition.fred_id:16} {len(series):>6} obs  {series.index[0].date()} -> {series.index[-1].date()}")

"""FRED fetching. I/O only — no transformation happens here."""

import os

import pandas as pd
import requests

BASE = "https://api.stlouisfed.org/fred/series/observations"
TIMEOUT = 30


class FredError(RuntimeError):
    """A FRED request or payload was unusable."""


def parse_observations(payload: dict) -> pd.Series:
    """Turn a FRED observations payload into a clean float series.

    FRED marks missing values with "." on market holidays; those rows are
    dropped rather than filled.
    """
    if "observations" not in payload:
        raise FredError(f"no observations in payload: {payload}")
    dates, values = [], []
    for obs in payload["observations"]:
        if obs["value"] == ".":
            continue
        dates.append(pd.Timestamp(obs["date"]))
        values.append(float(obs["value"]))
    return pd.Series(values, index=pd.DatetimeIndex(dates), name="value").sort_index()


def fetch(series_id: str, api_key: str | None = None) -> pd.Series:
    """Fetch a series' full history. One call returns everything."""
    key = api_key or os.environ.get("FRED_API_KEY")
    if not key:
        raise FredError("FRED_API_KEY is not set")
    params = {"series_id": series_id, "api_key": key, "file_type": "json"}
    try:
        response = requests.get(BASE, params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        # requests' exception strings embed the full request URL, api_key and
        # all, and load_levels puts whatever is raised here into a public page
        # and a public CI log. Only the series id and the exception type cross
        # this boundary. `from None` so a traceback cannot reattach the URL.
        raise FredError(f"{series_id}: {type(exc).__name__}") from None
    if response.status_code != 200:
        raise FredError(f"{series_id}: HTTP {response.status_code} {response.text[:200]}")
    return parse_observations(response.json())

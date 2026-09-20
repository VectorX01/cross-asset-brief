"""CFTC Commitments of Traders. No API key required."""

import pandas as pd
import requests

from brief.config import CONTRACTS

BASE = "https://publicreporting.cftc.gov/resource"
TIMEOUT = 60
LIMIT = 50000
DATE_FIELD = "report_date_as_yyyy_mm_dd"
MARKET_FIELD = "market_and_exchange_names"

DATASETS = {"tff": "gpe5-46if", "disagg": "72hh-3qpy"}

# (long field, short field) per report — verified against the live API.
FIELDS = {
    "tff": ("lev_money_positions_long", "lev_money_positions_short"),
    "disagg": ("m_money_positions_long_all", "m_money_positions_short_all"),
}


class CftcError(RuntimeError):
    """A CFTC request or payload was unusable."""


def parse_positions(rows: list[dict], report: str) -> pd.Series:
    """Net position (long minus short) per report date."""
    if report not in FIELDS:
        raise CftcError(f"unknown report: {report!r}")
    if not rows:
        raise CftcError("no rows returned")
    long_field, short_field = FIELDS[report]
    dates, values = [], []
    for row in rows:
        if long_field not in row or short_field not in row:
            continue
        dates.append(pd.Timestamp(row[DATE_FIELD][:10]))
        values.append(float(row[long_field]) - float(row[short_field]))
    if not values:
        raise CftcError(f"no rows carried {long_field}/{short_field}")
    return pd.Series(values, index=pd.DatetimeIndex(dates), name="net").sort_index()


def fetch(contract_key: str) -> pd.Series:
    contract = CONTRACTS[contract_key]
    params = {
        "$limit": LIMIT,
        "$where": f"{MARKET_FIELD}='{contract.market_code}'",
        "$order": f"{DATE_FIELD} ASC",
    }
    url = f"{BASE}/{DATASETS[contract.report]}.json"
    response = requests.get(url, params=params, timeout=TIMEOUT)
    if response.status_code != 200:
        raise CftcError(f"{contract_key}: HTTP {response.status_code} {response.text[:200]}")
    return parse_positions(response.json(), contract.report)

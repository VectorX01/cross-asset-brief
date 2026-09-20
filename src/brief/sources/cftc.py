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


def splice(series_list: list[pd.Series]) -> pd.Series:
    """Concatenate same-contract series recorded under different market names.

    The pieces must not share a date — CFTC's renames are documented as
    non-overlapping, and a duplicate date silently double-counting a week
    would otherwise be invisible in a percentile.
    """
    combined = pd.concat(series_list).sort_index()
    duplicates = combined.index[combined.index.duplicated()]
    if not duplicates.empty:
        raise CftcError(f"overlapping report date(s) across market codes: {list(duplicates)}")
    return combined


def _fetch_one(dataset: str, market_code: str, report: str) -> pd.Series:
    params = {
        "$limit": LIMIT,
        "$where": f"{MARKET_FIELD}='{market_code}'",
        "$order": f"{DATE_FIELD} ASC",
    }
    url = f"{BASE}/{dataset}.json"
    response = requests.get(url, params=params, timeout=TIMEOUT)
    if response.status_code != 200:
        raise CftcError(f"{market_code}: HTTP {response.status_code} {response.text[:200]}")
    return parse_positions(response.json(), report)


def fetch(contract_key: str) -> pd.Series:
    """Fetch a contract's full history, splicing across any market-name renames.

    Each market code is queried separately (rather than a SoQL `in(...)`
    clause) because some names contain commas and ampersands that would
    need careful quoting; per-name queries sidestep that at the cost of a
    few extra HTTP calls.
    """
    contract = CONTRACTS[contract_key]
    dataset = DATASETS[contract.report]
    try:
        pieces = [
            _fetch_one(dataset, market_code, contract.report)
            for market_code in contract.market_codes
        ]
    except requests.RequestException as exc:
        # Caught here rather than in _fetch_one because this is the level that
        # knows the contract key. Only that key and the exception type cross
        # the boundary: a raw requests exception string embeds the request URL,
        # and whatever is raised here is rendered on a public page and logged
        # in public CI. Same rule as fred.py, where the URL carries the key.
        raise CftcError(f"{contract_key}: {type(exc).__name__}") from None
    return splice(pieces)

"""Yahoo's chart endpoint, for prices FRED lags badly or does not carry.

FRED's crude series ran three days behind on a week when crude fell ten
percent, and it has no free daily gold at all. This covers equities,
commodities and FX; rates, credit and funding stay on FRED, which is both
official and more complete for them.

Used through plain `requests` rather than yfinance: the payload is a
timestamp array and a close array, and a dependency would add a breakage
layer without adding anything. Unofficial either way, which is why the
cross-check in `brief.crosscheck` exists.
"""

import time

import pandas as pd
import requests

BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
TIMEOUT = 30
# Yahoo refuses a request with no User-Agent, and says so only with a 429.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; cross-asset-brief/1.0)"}


class YahooError(RuntimeError):
    """A Yahoo request or payload was unusable."""


def parse_chart(payload: dict) -> pd.Series:
    """Daily closes, indexed by calendar date.

    Sessions with no print carry a null close and are dropped rather than
    filled. The index is normalised to midnight because Yahoo timestamps the
    session open in exchange-local time, and the board joins on dates.
    """
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise YahooError(str(chart["error"].get("description", chart["error"])))
    results = chart.get("result")
    if not results:
        raise YahooError("no result in payload")

    result = results[0]
    stamps = result.get("timestamp") or []
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close") or []
    if not stamps:
        raise YahooError(f"{result.get('meta', {}).get('symbol', '?')}: no observations")

    dates = [pd.Timestamp(s, unit="s", tz="UTC").tz_localize(None).normalize()
             for s, close in zip(stamps, closes) if close is not None]
    values = [float(close) for close in closes if close is not None]
    if not values:
        raise YahooError(f"{result.get('meta', {}).get('symbol', '?')}: no closes")

    return pd.Series(values, index=pd.DatetimeIndex(dates), name="close").sort_index()


def fetch(symbol: str, *, since: int = 0, interval: str = "1d") -> pd.Series:
    """One symbol's full daily history.

    Requested as an explicit date range rather than `range=max`, which
    silently downsamples to monthly -- 170 points across 42 years, all
    first-of-month. The metrics take 60-day rolling correlations and
    five-year percentiles, so monthly data would not fail loudly; it would
    just be wrong.
    """
    try:
        response = requests.get(
            f"{BASE}/{symbol}",
            params={
                "period1": since,
                "period2": int(time.time()) + 86400,
                "interval": interval,
            },
            headers=HEADERS,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        # Never the URL: it would put the query string on a public page.
        raise YahooError(f"{symbol}: {type(exc).__name__}") from None
    if response.status_code != 200:
        raise YahooError(f"{symbol}: HTTP {response.status_code}")
    return parse_chart(response.json())

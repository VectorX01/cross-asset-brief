"""I/O for the scheduled-events feeds. Parsing lives in `brief.calendar`.

Three endpoints, three shapes: FRED returns JSON, the Fed returns JSON behind
a UTF-8 BOM (so this hands back raw bytes), TreasuryDirect returns a JSON list.
"""

import os

import requests

FRED_RELEASES = "https://api.stlouisfed.org/fred/releases/dates"
FED_CALENDAR = "https://www.federalreserve.gov/json/calendar.json"
TREASURY_UPCOMING = "https://www.treasurydirect.gov/TA_WS/securities/upcoming"
TIMEOUT = 30
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; cross-asset-brief/1.0)"}


class ScheduleError(RuntimeError):
    """A schedule feed was unreachable or unusable."""


def _get(url: str, params: dict | None, what: str):
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        # Never the URL: the FRED one carries the api_key.
        raise ScheduleError(f"{what}: {type(exc).__name__}") from None
    if response.status_code != 200:
        raise ScheduleError(f"{what}: HTTP {response.status_code}")
    return response


def fred_release_dates(start: str, end: str, api_key: str | None = None) -> dict:
    """Scheduled release dates. Without include_release_dates_with_no_data the
    endpoint returns only releases that have already published, which makes it
    a history rather than a calendar."""
    key = api_key or os.environ.get("FRED_API_KEY")
    if not key:
        raise ScheduleError("FRED_API_KEY is not set")
    return _get(
        FRED_RELEASES,
        {
            "api_key": key,
            "file_type": "json",
            "realtime_start": start,
            "realtime_end": end,
            "include_release_dates_with_no_data": "true",
            "sort_order": "asc",
            "limit": 1000,
        },
        "FRED releases",
    ).json()


def fed_calendar() -> bytes:
    """Raw bytes: the feed is served with a BOM and must be decoded as utf-8-sig."""
    return _get(FED_CALENDAR, None, "Fed calendar").content


def treasury_upcoming() -> list[dict]:
    """Announced-but-not-yet-held auctions."""
    return _get(TREASURY_UPCOMING, {"format": "json"}, "Treasury auctions").json()

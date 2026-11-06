"""What's scheduled: data releases, Fed speakers, Treasury auctions.

Three public feeds, none of which needs a key beyond the FRED one already in
use:

- FRED's release calendar lists ~200 release dates in a given week, most of
  them daily data feeds nobody schedules around (Coinbase Cryptocurrencies,
  Dow Jones Averages). MARKET_MOVING is the filter; it is a judgment call and
  is meant to be edited.
- The Fed's own calendar.json carries FOMC meetings and every governor
  speech, with times. It is served with a UTF-8 BOM, which is why the parser
  takes bytes rather than a decoded string.
- TreasuryDirect lists announced auctions. The auction date lives in
  `competitiveAuctionCloseDate`; `auctionDate` is null until after the fact.

Earnings are deliberately absent. There is no free, stable, machine-readable
source for "the earnings that matter this week", and a scraped one would rot
silently — which is worse than an honest gap.
"""

import json
from dataclasses import dataclass

# Substring match, so "Employment Situation" catches whatever suffix FRED
# appends. Ordered roughly by how much the tape cares.
MARKET_MOVING: tuple[str, ...] = (
    "FOMC",
    "Employment Situation",
    "Consumer Price Index",
    "Producer Price Index",
    "Personal Income and Outlays",
    "Gross Domestic Product",
    "Retail Trade",
    "Job Openings",
    "Industrial Production",
    "New Residential Construction",
    "Consumer Sentiment",
    "Unemployment Insurance Weekly Claims",
    "ADP",
    "Treasury International Capital",
    "Senior Loan Officer",
)

KIND_ORDER = {"fed": 0, "data": 1, "auction": 2}


@dataclass(frozen=True)
class Event:
    date: str
    time: str
    kind: str
    label: str


def _topic(name: str) -> str | None:
    """Which watched release this is, if any."""
    for needle in MARKET_MOVING:
        if needle.lower() in name.lower():
            return needle
    return None


def parse_fred_releases(payload: dict, start: str, end: str) -> list[Event]:
    """FRED's release calendar, filtered to the releases a desk watches."""
    best: dict[str, tuple[str, str]] = {}
    for row in payload.get("release_dates", []):
        name, when = row.get("release_name", ""), row.get("date", "")
        if not (start <= when <= end):
            continue
        topic = _topic(name)
        if topic is None:
            continue
        # One row per topic. FRED lists CPI three times on the same day --
        # headline, an ex-energy cut, and a research series -- and a desk
        # watches one CPI. Earliest date wins; among names on that date the
        # shortest is the headline release rather than a derived cut.
        current = best.get(topic)
        if current is None or (when, len(name)) < (current[0], len(current[1])):
            best[topic] = (when, name)
    return [Event(date=when, time="", kind="data", label=name) for when, name in best.values()]


def parse_fed_calendar(raw: bytes, start: str, end: str) -> list[Event]:
    """FOMC meetings and Fed speakers. Served with a BOM, hence bytes in.

    An event's date is split across `month` ("2026-11") and `days` ("13"),
    and `days` is sometimes a range like "15-16" for a two-day FOMC, in which
    case the first day is the one that matters for a calendar.
    """
    payload = json.loads(raw.decode("utf-8-sig"))
    events = payload.get("events", payload) if isinstance(payload, dict) else payload

    out = []
    for event in events:
        month, days = str(event.get("month", "")), str(event.get("days", ""))
        if not month or not days:
            continue
        first = days.split("-")[0].strip()
        if not first.isdigit():
            continue
        when = f"{month}-{int(first):02d}"
        if start <= when <= end:
            out.append(
                Event(
                    date=when,
                    time=str(event.get("time", "")),
                    kind="fed",
                    label=str(event.get("title", "")),
                )
            )
    return out


def parse_auctions(rows: list[dict], start: str, end: str) -> list[Event]:
    """Announced Treasury auctions, with size — the number that moves the curve."""
    out = []
    for row in rows:
        when = str(row.get("competitiveAuctionCloseDate") or "")[:10]
        if not (start <= when <= end):
            continue
        term = str(row.get("securityTerm", "")).strip()
        kind = str(row.get("securityType", "")).strip()
        amount = row.get("offeringAmount")
        try:
            # Absent rather than "$0bn": bills are sometimes announced before
            # the size is set, and a zero would read as a real number.
            size = f" ${int(amount) / 1e9:.0f}bn" if amount else ""
        except (TypeError, ValueError):
            size = ""
        out.append(Event(date=when, time="", kind="auction", label=f"{term} {kind}{size}"))
    return out


def order(events: list[Event]) -> list[Event]:
    """By date, then Fed before data before auctions, then by label.

    One row per label. FRED emits a date per day for some releases, so
    "FOMC Press Release" arrives three days running; within a one-week window
    a release happens once, and listing it repeatedly buries everything else.
    The earliest date wins, and a feed carrying a time beats one that does not.
    """
    ranked = sorted(events, key=lambda e: (e.date, KIND_ORDER.get(e.kind, 9), not e.time, e.label))
    seen, unique = set(), []
    for event in ranked:
        if event.label in seen:
            continue
        seen.add(event.label)
        unique.append(event)
    return sorted(unique, key=lambda e: (e.date, KIND_ORDER.get(e.kind, 9), e.label))

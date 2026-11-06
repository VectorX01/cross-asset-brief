"""What the market has priced for the Fed, from 30-day fed funds futures.

CME FedWatch has no free API, but FedWatch is derived from these contracts,
so the inputs are available even though the product is not. A contract settles
at 100 minus the average effective fed funds rate over its delivery month, so
`100 - price` is the market's expected average EFFR for that month.

Deliberately quoted by month, not by meeting. A meeting mid-month splits the
contract between the old rate and the new one, and backing out a per-meeting
probability means assuming where in the month the change lands. That is the
step where FedWatch's precision comes from, and it is an assumption this page
does not need: "+13bp priced by March" says the same thing without pretending
to a decimal it has not earned.
"""

from dataclasses import dataclass
from datetime import date

# CME delivery-month codes, January through December.
MONTH_CODES = "FGHJKMNQUVXZ"


@dataclass(frozen=True)
class PathPoint:
    label: str
    symbol: str
    implied: float
    change_bp: float | None


def contract_symbol(year: int, month: int) -> str:
    """ZQ + month code + two-digit year, on the CBOT venue."""
    return f"ZQ{MONTH_CODES[month - 1]}{year % 100:02d}.CBT"


def next_contracts(today: date, count: int) -> list[tuple[str, str]]:
    """(label, symbol) for the next `count` delivery months, starting next month.

    The current month is skipped: most of it has already fixed, so its implied
    average says more about where the rate has been than where it is going.
    """
    out = []
    year, month = today.year, today.month
    for _ in range(count):
        month += 1
        if month > 12:
            month, year = 1, year + 1
        label = date(year, month, 1).strftime("%b %Y")
        out.append((label, contract_symbol(year, month)))
    return out


def implied_rate(price: float) -> float:
    """100 minus the price is the expected average EFFR for the month."""
    return 100.0 - price


def build_path(today: date, count: int, fetch, current: float | None) -> list[PathPoint]:
    """The priced path. A contract that will not fetch is left out, not faked."""
    points = []
    for label, symbol in next_contracts(today, count):
        try:
            price = fetch(symbol)
        except Exception:
            continue
        rate = implied_rate(price)
        points.append(
            PathPoint(
                label=label,
                symbol=symbol,
                implied=rate,
                change_bp=None if current is None else (rate - current) * 100.0,
            )
        )
    return points


def summarise(points: list[PathPoint]) -> str:
    """One sentence a reader can repeat: direction, size, and by when."""
    priced = [p for p in points if p.change_bp is not None]
    if not priced:
        return "No fed funds pricing available."
    last = priced[-1]
    size = abs(last.change_bp)
    if size < 5:
        return f"Nothing meaningful priced by {last.label} ({last.change_bp:+.0f}bp)."
    direction = "of hikes" if last.change_bp > 0 else "of cuts"
    return f"{size:.0f}bp {direction} priced by {last.label}."

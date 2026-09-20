"""Payload to HTML."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from brief.render.svg import percentile_strip, sparkline
from brief.text import ordinal
from brief.transforms import PRICE_LIKE

TEMPLATE_DIR = Path(__file__).parent

# How a headline number is written, keyed by Metric.unit. Formatting belongs
# here and not in the pipeline, which must stay metric-agnostic: the unit
# string is the only thing the render layer needs to know, and a new metric
# gets its formatting by declaring a unit rather than by editing a branch.
UNIT_FORMATS = {
    "corr": lambda v: f"{v:+.2f}",
    "pctile pts": lambda v: f"{v:+.0f} pctile pts",
    "contracts": lambda v: f"{v:+,.0f} contracts",
}


def format_value(value: float, unit: str) -> str:
    """The tile headline. An unknown unit still renders a number."""
    return UNIT_FORMATS.get(unit, lambda v: f"{v:+.2f}")(value)


# How each quote convention is written. A table rather than a cascade of ifs
# so adding an asset class is a row, and so the conventions sit together where
# they can be compared against how a desk actually says them.
LEVEL_FORMATS = {
    "index": lambda v: f"{v:,.2f}",
    "commodity": lambda v: f"{v:,.2f}",
    "fx": lambda v: f"{v:,.4f}",
    "fxjpy": lambda v: f"{v:,.2f}",
    "bp": lambda v: f"{v * 100:,.0f}bp",
    "points": lambda v: f"{v:,.2f}",
    "yield": lambda v: f"{v:,.2f}",
}

# Absolute-and-percent where a desk says both; percent alone for FX, where the
# absolute is pips and nobody quotes those in a macro conversation; basis
# points alone for anything rate-like, where a percent is meaningless.
CHANGE_FORMATS = {
    "index": lambda a, p: f"{a:+,.2f} ({p:+.2f}%)",
    "commodity": lambda a, p: f"{a:+,.2f} ({p:+.2f}%)",
    "points": lambda a, p: f"{a:+,.2f} ({p:+.1f}%)",
    "fx": lambda a, p: f"{p:+.2f}%",
    "fxjpy": lambda a, p: f"{p:+.2f}%",
    "bp": lambda a, p: f"{a * 100:+,.0f}bp",
    "yield": lambda a, p: f"{a * 100:+,.0f}bp",
}


def level_text(row) -> str:
    """The number as a desk would write it."""
    return LEVEL_FORMATS[row.quote](row.level)


def change_text(absolute: float | None, percent: float | None, quote: str) -> str:
    """No move is an em dash: "only one observation" and "it did not move"
    are different facts and the board should not conflate them."""
    if absolute is None:
        return "—"
    return CHANGE_FORMATS[quote](absolute, percent)


def move_direction(absolute: float | None) -> str:
    """Green up, red down -- direction, not judgment. A yield rising is green
    whether or not that is good news for whoever is reading."""
    if absolute is None or absolute == 0:
        return "flat"
    return "up" if absolute > 0 else "down"


def range_text(row) -> str:
    """The trailing-year low and high, in the row's own convention.

    A negative low takes "to" rather than an en dash: "-3–100bp" sets a
    minus sign against a dash and reads as a typo.
    """
    joiner = " to " if row.low_1y < 0 else "–"
    if row.quote == "bp":
        return f"{row.low_1y * 100:,.0f}{joiner}{row.high_1y * 100:,.0f}bp"
    fmt = LEVEL_FORMATS[row.quote]
    return f"{fmt(row.low_1y)}{joiner}{fmt(row.high_1y)}"


def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["strip"] = lambda pct: _markup(percentile_strip(pct))
    env.globals["spark"] = lambda values: _markup(sparkline(values))
    env.filters["ordinal"] = ordinal
    env.globals["value"] = format_value
    env.globals["level"] = level_text
    env.globals["change"] = change_text
    env.globals["span"] = range_text
    env.globals["direction"] = move_direction
    return env


def _markup(svg: str):
    from markupsafe import Markup

    return Markup(svg)


def render(payload: dict) -> str:
    return _environment().get_template("template.html").render(payload=payload)

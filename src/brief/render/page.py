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


def level_text(row) -> str:
    """The number as a desk would write it."""
    if row.quote == "price":
        return f"{row.level:,.1f}"
    if row.quote == "bp":
        return f"{row.level * 100:,.0f}bp"
    return f"{row.level:.2f}"


def change_text(value: float | None, quote: str) -> str:
    """No move is an em dash: "only one observation" and "it did not move"
    are different facts and the board should not conflate them."""
    if value is None:
        return "—"
    if quote == "price":
        return f"{value:+.1f}%"
    if quote == "points":
        return f"{value:+.2f}"
    return f"{value * 100:+.0f}bp"


def range_text(row) -> str:
    """The trailing-year low and high, in the row's own convention.

    A negative low takes "to" rather than an en dash: "-3–100bp" sets a
    minus sign against a dash and reads as a typo.
    """
    joiner = " to " if row.low_1y < 0 else "–"
    if row.quote == "price":
        return f"{row.low_1y:,.0f}{joiner}{row.high_1y:,.0f}"
    if row.quote == "bp":
        return f"{row.low_1y * 100:,.0f}{joiner}{row.high_1y * 100:,.0f}bp"
    if row.quote == "points":
        return f"{row.low_1y:.1f}{joiner}{row.high_1y:.1f}"
    return f"{row.low_1y:.2f}{joiner}{row.high_1y:.2f}"


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
    return env


def _markup(svg: str):
    from markupsafe import Markup

    return Markup(svg)


def render(payload: dict) -> str:
    return _environment().get_template("template.html").render(payload=payload)

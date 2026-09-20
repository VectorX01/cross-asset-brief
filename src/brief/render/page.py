"""Payload to HTML."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from brief.render.svg import percentile_strip, sparkline
from brief.text import ordinal

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
    return env


def _markup(svg: str):
    from markupsafe import Markup

    return Markup(svg)


def render(payload: dict) -> str:
    return _environment().get_template("template.html").render(payload=payload)

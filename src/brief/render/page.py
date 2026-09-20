"""Payload to HTML."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from brief.render.svg import percentile_strip, sparkline
from brief.text import ordinal

TEMPLATE_DIR = Path(__file__).parent


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
    return env


def _markup(svg: str):
    from markupsafe import Markup

    return Markup(svg)


def render(payload: dict) -> str:
    return _environment().get_template("template.html").render(payload=payload)

"""The metric registry.

`interpret` is a required field, not an optional one. A metric that cannot
state what it means in one sentence cannot be registered — the explainability
constraint is enforced here rather than left to discipline.
"""

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

Interpreter = Callable[[float, float], str]


@dataclass(frozen=True)
class Metric:
    name: str
    title: str
    inputs: tuple[str, ...]
    context_window: int | None
    fn: Callable[[dict[str, pd.Series]], pd.Series]
    interpret: Interpreter
    unit: str
    # Why this metric is on the page at all, and what a reader should take
    # from it. Required for the same reason `interpret` is: a metric nobody
    # can justify in two sentences does not belong on a page whose purpose is
    # teaching the reader what they are looking at.
    why: str
    implication: str
    # What the layout should do with this metric, if anything special.
    # "setup" gets its own block above the grid. Declared here so the
    # pipeline can ask the registry what a metric is for instead of
    # branching on its name -- renaming a metric must not silently change
    # the page.
    role: str | None = None


REGISTRY: dict[str, Metric] = {}


def register(metric: Metric) -> Metric:
    if metric.name in REGISTRY:
        raise ValueError(f"duplicate metric name: {metric.name}")
    REGISTRY[metric.name] = metric
    return metric

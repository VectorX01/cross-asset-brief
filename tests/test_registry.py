"""The registry's contract: a metric that cannot explain itself cannot register."""

import pandas as pd
import pytest

from brief.metrics import cross_asset, positioning  # noqa: F401  (registers metrics)
from brief.metrics.registry import REGISTRY, Metric


def _fields(**overrides):
    base = dict(
        name="probe",
        title="Probe",
        inputs=("equity",),
        context_window=None,
        fn=lambda levels: pd.Series(dtype=float),
        interpret=lambda value, pctile: "a sentence",
        unit="",
        why="what this measures",
        implication="what to conclude",
    )
    base.update(overrides)
    return base


def test_a_metric_declaring_everything_constructs():
    assert Metric(**_fields()).why == "what this measures"


def test_a_metric_without_a_why_cannot_be_constructed():
    fields = _fields()
    del fields["why"]
    with pytest.raises(TypeError):
        Metric(**fields)


def test_a_metric_without_an_implication_cannot_be_constructed():
    fields = _fields()
    del fields["implication"]
    with pytest.raises(TypeError):
        Metric(**fields)


def test_every_registered_metric_explains_what_it_measures():
    missing = [name for name, m in REGISTRY.items() if not m.why.strip()]
    assert missing == []


def test_every_registered_metric_states_what_to_conclude():
    missing = [name for name, m in REGISTRY.items() if not m.implication.strip()]
    assert missing == []


def test_explanations_are_prose_not_restatements_of_the_title():
    """A `why` that merely echoes the title teaches the reader nothing."""
    echoes = [
        name
        for name, m in REGISTRY.items()
        if m.why.strip().lower().rstrip(".") == m.title.strip().lower()
    ]
    assert echoes == []

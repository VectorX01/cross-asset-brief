"""Positioning and flows. CoT is weekly and three days stale on arrival:
it contextualises rather than triggers."""

import pandas as pd

from brief.config import (
    CONTRACTS,
    DIVERGENCE_PCTILE,
    POSITIONING_WINDOW_YEARS,
)
from brief.metrics.registry import Metric, register
from brief.text import ordinal
from brief.transforms import percentile_rank

WEEKS_PER_YEAR = 52
POSITIONING_WINDOW = POSITIONING_WINDOW_YEARS * WEEKS_PER_YEAR
PRICE_WINDOW_DAYS = 63  # three months of trading days
DIVERGENCE_CONTRACT = "es"


def _positioning_fn(contract_key: str):
    def fn(levels: dict[str, pd.Series]) -> pd.Series:
        return levels[f"cot_{contract_key}"]

    return fn


def _interpret_positioning(label: str):
    def interpret(value: float, pctile: float) -> str:
        side = "long" if value > 0 else "short"
        if pctile >= 90:
            return (
                f"{label}: net {side} {abs(value):,.0f} contracts, {ordinal(pctile)} "
                "percentile of three years — a crowded position."
            )
        if pctile <= 10:
            return (
                f"{label}: net {side} {abs(value):,.0f} contracts, {ordinal(pctile)} "
                "percentile of three years — a crowded position on the other side."
            )
        return (
            f"{label}: net {side} {abs(value):,.0f} contracts, {ordinal(pctile)} "
            "percentile of three years."
        )

    return interpret


for _key, _contract in CONTRACTS.items():
    register(
        Metric(
            name=f"pos_{_key}",
            title=f"Positioning — {_contract.label}",
            inputs=(f"cot_{_key}",),
            context_window=POSITIONING_WINDOW,
            fn=_positioning_fn(_key),
            interpret=_interpret_positioning(_contract.label),
            unit="contracts",
        )
    )


def _divergence(levels: dict[str, pd.Series]) -> pd.Series:
    """Positioning percentile minus price percentile, evaluated each CoT week.

    Positive means crowded long into weak price; negative means crowded short
    into strong price.
    """
    net = levels[f"cot_{DIVERGENCE_CONTRACT}"].dropna().sort_index()
    price = levels[CONTRACTS[DIVERGENCE_CONTRACT].price_series].dropna().sort_index()
    out = {}
    for stamp in net.index:
        pos_hist = net.loc[:stamp]
        price_hist = price.loc[:stamp]
        if len(pos_hist) < 2 or len(price_hist) < 2:
            continue
        pos_pct = percentile_rank(pos_hist, window=POSITIONING_WINDOW)
        price_pct = percentile_rank(price_hist, window=PRICE_WINDOW_DAYS)
        out[stamp] = pos_pct - price_pct
    return pd.Series(out, name="divergence").dropna()


def _interpret_divergence(value: float, pctile: float) -> str:
    if pctile >= DIVERGENCE_PCTILE:
        return (
            f"Leveraged funds are {value:.0f} percentile points longer than price "
            f"justifies ({ordinal(pctile)} percentile of its own history) — a rally "
            "without sponsorship, vulnerable to long liquidation."
        )
    if pctile <= 100 - DIVERGENCE_PCTILE:
        return (
            f"Leveraged funds are {abs(value):.0f} percentile points shorter than "
            f"price justifies ({ordinal(pctile)} percentile of its own history) — a "
            "selloff without capitulation, vulnerable to a squeeze."
        )
    return (
        f"Positioning and price agree within {abs(value):.0f} percentile points — "
        "no divergence worth trading."
    )


divergence = register(
    Metric(
        name="divergence",
        title="Positioning-price divergence",
        inputs=(f"cot_{DIVERGENCE_CONTRACT}", CONTRACTS[DIVERGENCE_CONTRACT].price_series),
        context_window=None,
        fn=_divergence,
        interpret=_interpret_divergence,
        unit="pctile pts",
    )
)

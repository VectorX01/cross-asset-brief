"""Cross-asset relationship metrics."""

import pandas as pd

from brief.config import (
    COMOVEMENT_BASKET,
    CORR_WINDOW,
    SERIES,
    STRESS_WINDOW_YEARS,
    TRADING_DAYS_PER_YEAR,
)
from brief.metrics.registry import Metric, register
from brief.text import ordinal
from brief.transforms import (
    align,
    mean_abs_pairwise_corr,
    rolling_corr,
    rolling_percentile,
    to_change,
)

STRESS_WINDOW = STRESS_WINDOW_YEARS * TRADING_DAYS_PER_YEAR


def _stock_bond(levels: dict[str, pd.Series]) -> pd.Series:
    equity = to_change(levels["equity"], SERIES["equity"].kind)
    yields = to_change(levels["ust10"], SERIES["ust10"].kind)
    return rolling_corr(equity, yields, CORR_WINDOW)


def _interpret_stock_bond(value: float, pctile: float) -> str:
    if value > 0:
        return (
            f"Nasdaq and 10y yields are moving together ({value:+.2f}) — "
            "a growth-driven tape, and bonds are not hedging equities."
        )
    return (
        f"Nasdaq and 10y yields are moving inversely ({value:+.2f}) — "
        "a rate-driven tape, and bonds are hedging equities."
    )


stock_bond_regime = register(
    Metric(
        name="stock_bond",
        title="Nasdaq vs 10y regime",
        inputs=("equity", "ust10"),
        context_window=None,
        fn=_stock_bond,
        interpret=_interpret_stock_bond,
        unit="corr",
    )
)


def _credit_vs_vol(levels: dict[str, pd.Series]) -> pd.Series:
    credit = rolling_percentile(levels["credit"], STRESS_WINDOW).rename("credit")
    vix = rolling_percentile(levels["vix"], STRESS_WINDOW).rename("vix")
    joined = align(credit, vix)
    return joined["credit"] - joined["vix"]


def _interpret_credit_vs_vol(value: float, pctile: float) -> str:
    if value > 0:
        return (
            f"Credit is {abs(value):.0f} percentile points more stressed than equity "
            "vol — the two markets disagree, and one of them is wrong."
        )
    return (
        f"Equity vol is {abs(value):.0f} percentile points more stressed than "
        "credit — the two markets disagree, and one of them is wrong."
    )


def _comovement(levels: dict[str, pd.Series]) -> pd.Series:
    changes = [
        to_change(levels[name], SERIES[name].kind).rename(name)
        for name in COMOVEMENT_BASKET
    ]
    return mean_abs_pairwise_corr(align(*changes), CORR_WINDOW)


def _interpret_comovement(value: float, pctile: float) -> str:
    if pctile >= 70:
        return (
            f"Mean pairwise correlation {value:.2f} — assets are trading as one "
            "macro factor, so diversification is not working today."
        )
    if pctile <= 30:
        return (
            f"Mean pairwise correlation {value:.2f} — assets are telling unrelated "
            "stories, so single-name and relative-value risk dominates."
        )
    return (
        f"Mean pairwise correlation {value:.2f} — {ordinal(pctile)} percentile of "
        "its own history."
    )


credit_vs_vol = register(
    Metric(
        name="credit_vs_vol",
        title="Credit vs vol divergence",
        inputs=("credit", "vix"),
        context_window=None,
        fn=_credit_vs_vol,
        interpret=_interpret_credit_vs_vol,
        unit="pctile pts",
    )
)

comovement = register(
    Metric(
        name="comovement",
        title="Cross-asset co-movement",
        inputs=COMOVEMENT_BASKET,
        context_window=None,
        fn=_comovement,
        interpret=_interpret_comovement,
        unit="corr",
    )
)

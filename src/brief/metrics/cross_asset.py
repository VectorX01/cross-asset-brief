"""Cross-asset relationship metrics."""

import pandas as pd

from brief.config import CORR_WINDOW, SERIES
from brief.metrics.registry import Metric, register
from brief.transforms import rolling_corr, to_change


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

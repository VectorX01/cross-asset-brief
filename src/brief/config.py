"""Series and contract definitions. The single place ids are written down."""

from dataclasses import dataclass

from brief.transforms import PRICE_LIKE, RATE_LIKE

CORR_WINDOW = 60
POSITIONING_WINDOW_YEARS = 3
STRESS_WINDOW_YEARS = 5
TRADING_DAYS_PER_YEAR = 252
DIVERGENCE_THRESHOLD = 50.0


@dataclass(frozen=True)
class SeriesDef:
    fred_id: str
    label: str
    kind: str


SERIES: dict[str, SeriesDef] = {
    "equity": SeriesDef("WILL5000IND", "Wilshire 5000", PRICE_LIKE),
    "ust10": SeriesDef("DGS10", "10y Treasury yield", RATE_LIKE),
    "ust2": SeriesDef("DGS2", "2y Treasury yield", RATE_LIKE),
    "usd": SeriesDef("DTWEXBGS", "Broad dollar index", PRICE_LIKE),
    "hy": SeriesDef("BAMLH0A0HYM2", "HY OAS", RATE_LIKE),
    "ig": SeriesDef("BAMLC0A0CM", "IG OAS", RATE_LIKE),
    "vix": SeriesDef("VIXCLS", "VIX", RATE_LIKE),
    "wti": SeriesDef("DCOILWTICO", "WTI crude", PRICE_LIKE),
}

COMOVEMENT_BASKET = ("equity", "ust10", "usd", "hy", "wti", "vix")

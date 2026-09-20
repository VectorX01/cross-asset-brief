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


# equity: WILL5000IND is gone from FRED entirely (confirmed 400 on both
# WILL5000IND and WILL5000INDFC). NASDAQCOM is the only free long-history
# daily US equity index left on FRED, and metric 1's value depends on
# spanning the pre-2020 negative stock-bond correlation era. SP500's 10y
# cap is ample for the 3-month price percentile that the E-mini S&P
# divergence metric needs, and matches that contract far better than
# Nasdaq, so it is kept as a separate series rather than folded into
# "equity".
#
# credit: BAMLH0A0HYM2/BAMLC0A0CM (HY/IG OAS) are both now capped to 3
# years of history by an ICE licensing change. BAA10Y has a 40-year
# history and supports STRESS_WINDOW_YEARS = 5. No metric consumes "ig",
# so it is dropped rather than replaced.
SERIES: dict[str, SeriesDef] = {
    "equity": SeriesDef("NASDAQCOM", "Nasdaq Composite", PRICE_LIKE),
    "spx": SeriesDef("SP500", "S&P 500", PRICE_LIKE),
    "ust10": SeriesDef("DGS10", "10y Treasury yield", RATE_LIKE),
    "ust2": SeriesDef("DGS2", "2y Treasury yield", RATE_LIKE),
    "usd": SeriesDef("DTWEXBGS", "Broad dollar index", PRICE_LIKE),
    "credit": SeriesDef("BAA10Y", "Baa corporate spread over 10y", RATE_LIKE),
    "vix": SeriesDef("VIXCLS", "VIX", RATE_LIKE),
    "wti": SeriesDef("DCOILWTICO", "WTI crude", PRICE_LIKE),
}

COMOVEMENT_BASKET = ("equity", "ust10", "usd", "credit", "wti", "vix")


def source_of(key: str) -> str:
    """Which public API a levels key came from."""
    if key.startswith("cot_"):
        return "CFTC"
    if key in SERIES:
        return "FRED"
    raise KeyError(f"unknown levels key: {key}")


@dataclass(frozen=True)
class ContractDef:
    report: str          # "tff" or "disagg"
    market_code: str     # exact market_and_exchange_names value
    label: str
    price_series: str | None   # key into SERIES, or None if no free daily price


# price_series for "es" is "spx" (S&P 500), not "equity" (Nasdaq Composite):
# SERIES["equity"] became NASDAQCOM after FRED dropped the Wilshire index,
# and "spx" -> SP500 was added specifically to pair with this contract.
# Pairing E-mini S&P positioning against a Nasdaq price would be wrong.
#
# wti's market_code is "WTI-PHYSICAL", not "CRUDE OIL, LIGHT SWEET": CFTC
# renamed the flagship NYMEX WTI contract on 2022-02-08 (confirmed via the
# live API — "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE" has no
# reports after 2022-02-01; "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE"
# has the same ~2M-contract open interest starting the next report week and
# continues to the present. It is the same contract under its current name.
CONTRACTS: dict[str, ContractDef] = {
    "es": ContractDef(
        "tff", "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE", "E-mini S&P 500", "spx"
    ),
    "ust10": ContractDef(
        "tff", "UST 10Y NOTE - CHICAGO BOARD OF TRADE", "10y Treasury note", "ust10"
    ),
    "dxy": ContractDef("tff", "USD INDEX - ICE FUTURES U.S.", "US Dollar Index", "usd"),
    "gold": ContractDef("disagg", "GOLD - COMMODITY EXCHANGE INC.", "Gold", None),
    "wti": ContractDef(
        "disagg", "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE", "WTI crude", "wti"
    ),
}

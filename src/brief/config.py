"""Series and contract definitions. The single place ids are written down."""

from dataclasses import dataclass

from brief.transforms import PRICE_LIKE, RATE_LIKE

CORR_WINDOW = 60
POSITIONING_WINDOW_YEARS = 3
STRESS_WINDOW_YEARS = 5
TRADING_DAYS_PER_YEAR = 252
# One symmetric band, in percentile space, for every tile that claims a
# reading is notable: a tile speaks up only when today's value sits in either
# tail of its OWN history (not against a raw threshold -- percentile is the
# only vocabulary, and a threshold on raw magnitude would compare unlike
# things). 90/10 rather than anything looser because the claim these tiles
# make in the tails is a strong one ("diversification is not working today",
# "vulnerable to long liquidation"), and a reading two days in five is not
# evidence for it: 90/10 fires on roughly one day in five across the two
# tails combined. Shared by divergence, co-movement and positioning so that
# "notable" means one thing across the page rather than three.
NOTABLE_PCTILE = 90.0


# How a number is written on the board. Deliberately separate from `kind`,
# which decides the differencing rule: VIX is rate-like for the maths (first
# differences) but is quoted in vol points, and nobody writes 2s10s as 0.27.
SOURCES = frozenset({"FRED", "YAHOO", "ECB"})
QUOTES = frozenset({"index", "fx", "fxjpy", "commodity", "yield", "bp", "points"})
QUOTE_FOR_KIND = {PRICE_LIKE: "index", RATE_LIKE: "yield"}


@dataclass(frozen=True)
class SeriesDef:
    series_id: str
    label: str
    kind: str
    # How many days old this series' newest observation may be before a tile
    # that depends on it is marked stale. A property of the series' own
    # publication lag, not of any metric that consumes it. Defaulted field
    # must come last on a frozen dataclass.
    stale_after_days: int = 5
    quote: str | None = None
    source: str = "FRED"
    # A series elsewhere that should track this one. Compared on every
    # build, because an unofficial source is only defensible if checked.
    cross_check: str | None = None

    def __post_init__(self):
        if self.quote is None:
            object.__setattr__(self, "quote", QUOTE_FOR_KIND[self.kind])
        elif self.quote not in QUOTES:
            # Unknown quotes would fall through the formatters' default and
            # render as a yield -- silently, which is how a 2.27-point VIX
            # move once printed as -227bp.
            raise ValueError(f"{self.series_id}: unknown quote {self.quote!r}")
        if self.source not in SOURCES:
            raise ValueError(f"{self.series_id}: unknown source {self.source!r}")


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
    # Equities. Yahoo rather than FRED: FRED's index series run ~3 days behind,
    # and an index close is an index close — the adjustment-methodology worry
    # that dogs Yahoo applies to individual stocks, not to index levels.
    "equity": SeriesDef("^IXIC", "Nasdaq Composite", PRICE_LIKE, quote="index",
                        source="YAHOO", cross_check="NASDAQCOM"),
    "spx": SeriesDef("^GSPC", "S&P 500", PRICE_LIKE, quote="index",
                     source="YAHOO", cross_check="SP500"),

    # The Treasury curve. FRED: official, and Yahoo carries only three tenors.
    # Short labels because the board prints eleven in a row; the source-failure
    # header prints the id alongside, so "FRED 10y (DGS10)" stays unambiguous.
    "ust1mo": SeriesDef("DGS1MO", "1m", RATE_LIKE),
    "ust3mo": SeriesDef("DGS3MO", "3m", RATE_LIKE),
    "ust6mo": SeriesDef("DGS6MO", "6m", RATE_LIKE),
    "ust1": SeriesDef("DGS1", "1y", RATE_LIKE),
    "ust2": SeriesDef("DGS2", "2y", RATE_LIKE),
    "ust3": SeriesDef("DGS3", "3y", RATE_LIKE),
    "ust5": SeriesDef("DGS5", "5y", RATE_LIKE),
    "ust7": SeriesDef("DGS7", "7y", RATE_LIKE),
    "ust10": SeriesDef("DGS10", "10y", RATE_LIKE, cross_check="^TNX"),
    "ust20": SeriesDef("DGS20", "20y", RATE_LIKE),
    "ust30": SeriesDef("DGS30", "30y", RATE_LIKE),

    # 10y nominal decomposes exactly: real + breakeven. Answers "growth scare
    # or inflation scare?", which have opposite implications for equities.
    "real10": SeriesDef("DFII10", "10y real", RATE_LIKE),
    "be10": SeriesDef("T10YIE", "10y breakeven", RATE_LIKE),

    # Funding. Where stress shows before it reaches price.
    "sofr": SeriesDef("SOFR", "SOFR", RATE_LIKE),
    "effr": SeriesDef("EFFR", "EFFR", RATE_LIKE),
    "iorb": SeriesDef("IORB", "IORB", RATE_LIKE),

    # Credit. HY and IG carry only 3y of history since an ICE licensing change,
    # which is plenty for a board row and too little for a 5y percentile — so
    # they appear here but feed no metric. BAA10Y does the analytical work.
    "hy": SeriesDef("BAMLH0A0HYM2", "HY OAS", RATE_LIKE, quote="bp"),
    "ig": SeriesDef("BAMLC0A0CM", "IG OAS", RATE_LIKE, quote="bp"),
    "credit": SeriesDef("BAA10Y", "Baa over 10y", RATE_LIKE, quote="bp"),

    # FX. Yahoo is same-day; FRED's H.10 release runs about nine days behind.
    "eurusd": SeriesDef("EURUSD=X", "EURUSD", PRICE_LIKE, quote="fx", source="YAHOO"),
    "usdjpy": SeriesDef("JPY=X", "USDJPY", PRICE_LIKE, quote="fxjpy", source="YAHOO"),
    # No Yahoo equivalent of the Fed's broad trade-weighted index.
    "usd": SeriesDef("DTWEXBGS", "Broad dollar", PRICE_LIKE, stale_after_days=12),

    "vix": SeriesDef("VIXCLS", "VIX", RATE_LIKE, quote="points"),

    # Two different instruments, labelled as such rather than conflated:
    # `crude` is the front-month future (board), `wti` is spot Cushing, which
    # is the cleaner series for a correlation and feeds the co-movement metric.
    "crude": SeriesDef("CL=F", "WTI front-month", PRICE_LIKE, quote="commodity",
                       source="YAHOO", cross_check="DCOILWTICO"),
    "wti": SeriesDef("DCOILWTICO", "WTI spot", PRICE_LIKE, quote="commodity",
                     stale_after_days=8),
    "gold": SeriesDef("GC=F", "Gold", PRICE_LIKE, quote="commodity", source="YAHOO"),
}

COMOVEMENT_BASKET = ("equity", "ust10", "usd", "credit", "wti", "vix")

# The levels board: reference, not analysis. Sections render in this order,
# and a key that failed to load is simply absent rather than blank.
BOARD_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Equities", ("equity", "spx")),
    (
        "Treasury curve",
        (
            "ust1mo", "ust3mo", "ust6mo", "ust1", "ust2", "ust3",
            "ust5", "ust7", "ust10", "ust20", "ust30",
        ),
    ),
    ("Other", ("usd", "credit", "vix", "wti")),
)

# (display label, section, short leg, long leg). The spread is long minus short,
# which is how these are quoted: 2s10s positive means the curve is upward sloping.
BOARD_SPREADS: tuple[tuple[str, str, str, str], ...] = (
    ("2s10s", "Treasury curve", "ust2", "ust10"),
    ("3m10y", "Treasury curve", "ust3mo", "ust10"),
)


def source_of(key: str) -> str:
    """Which public API a levels key came from."""
    if key.startswith("cot_"):
        return "CFTC"
    return SERIES[key].source


# Which speculative category each report reports. The two are not
# interchangeable and the category is a property of the report, not a label
# choice: financial futures come from the Traders in Financial Futures
# report, physical commodities from the disaggregated report. Naming the
# wrong one on a page read by a front-office audience is the most costly
# error available here, so every sentence derives the category from this.
TRADER_CATEGORY = {"tff": "leveraged funds", "disagg": "managed money"}


@dataclass(frozen=True)
class ContractDef:
    report: str                  # "tff" or "disagg"
    market_codes: tuple[str, ...]  # exact market_and_exchange_names values, oldest first
    label: str
    price_series: str | None   # key into SERIES, or None if no free daily price

    @property
    def trader_category(self) -> str:
        return TRADER_CATEGORY[self.report]


# price_series for "es" is "spx" (S&P 500), not "equity" (Nasdaq Composite):
# SERIES["equity"] became NASDAQCOM after FRED dropped the Wilshire index,
# and "spx" -> SP500 was added specifically to pair with this contract.
# Pairing E-mini S&P positioning against a Nasdaq price would be wrong.
#
# CFTC renamed es, ust10, dxy and wti's market_and_exchange_names on
# 2022-02-08 (confirmed via the live API): the old name's last report is
# 2022-02-01 and the new name's first report is 2022-02-08, with matching
# open interest across the boundary and no gap or overlap. Each pair is one
# continuous series under two names, so market_codes lists both, oldest
# first: 817 pre-rename reports (2006-06-13 -> 2022-02-01) + 241
# post-rename reports (2022-02-08 -> 2026-09-15) = 1058, exactly matching
# gold's report count, which was never renamed and needs only one name.
CONTRACTS: dict[str, ContractDef] = {
    "es": ContractDef(
        "tff",
        (
            "E-MINI S&P 500 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE",
            "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
        ),
        "E-mini S&P 500",
        "spx",
    ),
    "ust10": ContractDef(
        "tff",
        (
            "10-YEAR U.S. TREASURY NOTES - CHICAGO BOARD OF TRADE",
            "UST 10Y NOTE - CHICAGO BOARD OF TRADE",
        ),
        "10y Treasury note",
        "ust10",
    ),
    "dxy": ContractDef(
        "tff",
        (
            "U.S. DOLLAR INDEX - ICE FUTURES U.S.",
            "USD INDEX - ICE FUTURES U.S.",
        ),
        "US Dollar Index",
        "usd",
    ),
    "gold": ContractDef("disagg", ("GOLD - COMMODITY EXCHANGE INC.",), "Gold", None),
    "wti": ContractDef(
        "disagg",
        (
            "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE",
            "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",
        ),
        "WTI crude",
        "wti",
    ),
}

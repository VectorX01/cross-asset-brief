# Cross-Asset Daily Brief — Design

Date: 2026-09-20
Status: approved design, pre-implementation

## Purpose

A once-daily cross-asset macro brief, read top to bottom in ninety seconds, that
surfaces what is *unusual* today rather than what the levels are.

Two audiences, in priority order:

1. The author, daily, to build genuine cross-asset market fluency.
2. A hiring manager, occasionally, as evidence of market thinking — via a public
   code repository, not via the live site.

The move it supports is risk seat to front office. That lens governs the design:
the brief surfaces asymmetry, not state. It deliberately avoids anything that
reads as risk reporting.

## Governing constraints

These are design filters. Any proposed feature that fails one is cut.

**The Yahoo test.** Every tile must show something unobtainable from a consumer
finance widget. A tile that shows a level or a price fails. A tile earns its
place only as a percentile, a positioning extreme, a cross-asset relationship,
or a plumbing quantity.

**Explainability.** No fitted parameters anywhere in the system. Correlations,
percentile ranks, and threshold rules only. Every metric must state its meaning
in one sentence, and that sentence is a required field of the metric definition
rather than text in a template. A metric that cannot explain itself cannot be
registered.

Explicitly rejected on these grounds, with reasons:

- *PCA / cross-asset PC1* — sign-flipping loadings, rotation ambiguity, and
  "percent variance explained today" is undefined without a window. Replaced by
  mean pairwise absolute correlation, which answers the same question in one
  sentence.
- *Dollar vs rate-differential residual* — a regression residual, and the free
  stack has no daily foreign 2y yields to feed it.
- *GARCH, Nelson-Siegel-Svensson fits* — fitted parameters, and out of scope for
  the chosen metric families.
- *Z-scores* — assume a stationarity the author cannot verify at a glance.
  Percentile rank answers the same question, survives fat tails, and explains
  itself. Percentile is the single vocabulary of the entire dashboard, which is
  also what makes ranking heterogeneous metrics against each other legitimate.

**Simplicity.** No database, no persistent store, no second repository, no
object storage. The daily run is stateless. DRY applies, but shared abstraction
is introduced only where duplication actually exists.

## Scope

**In (v1):** two data sources (FRED, CFTC), six metrics across two families
(cross-asset relationships, positioning and flows), an anomaly ranker, a static
single-page render, automated daily deployment.

**Out (v1), deliberately:**

- *Intraday anything.* The free macro stack publishes once a day; a refresh
  button would be decorative. Accepted by the author.
- *The view log* — a dated append-only record of views and reasoning, scored
  over time. Judged the highest-leverage feature for the author's goal, but it
  needs writes, and a static site cannot take them. First v2 feature; Cloudflare
  Worker + D1 handles it for $0.
- *Vintage / point-in-time storage.* Would change zero displayed numbers here —
  the series used are published rates, not revised aggregates. Recoverable later
  via FRED's ALFRED if the research harness ever needs it.
- *Volatility structure and curve structure families*, and the plumbing family.
  v2 candidates.
- *Any job-search integration.* Contrived; explicitly dropped.

## Data sources

Two sources. One key. No vendor redistribution constraints.

**FRED** (`api.stlouisfed.org/fred/`, free key, 120 req/min, `file_type=json`).
Full history returns in a single call per series, which is what makes the
stateless design work.

| Role | Series ID |
|---|---|
| Equity | `WILL5000IND` |
| 10y yield | `DGS10` |
| 2y yield | `DGS2` |
| Broad dollar | `DTWEXBGS` |
| HY credit spread | `BAMLH0A0HYM2` |
| IG credit spread | `BAMLC0A0CM` |
| Equity vol | `VIXCLS` |
| Crude | `DCOILWTICO` |

`WILL5000IND` is used rather than `SP500` because FRED caps `SP500` at ten years
by licensing, which would silently break every percentile claiming a long
context window. Every series ID above must be verified against the live API
during implementation — including actual start dates, which determine whether
the stated context windows are honest.

**CFTC** (Socrata, `publicreporting.cftc.gov/resource/{id}.json`, no key
required, `$limit` up to 50000, released Fridays ~15:30 ET with positions as of
the prior Tuesday).

The two reports are not interchangeable and the correct one depends on the
contract:

| Contract | Report | Dataset | Trader category |
|---|---|---|---|
| E-mini S&P 500 | TFF | `gpe5-46if` | Leveraged funds |
| 10y Treasury note | TFF | `gpe5-46if` | Leveraged funds |
| US Dollar Index | TFF | `gpe5-46if` | Leveraged funds |
| Gold | Disaggregated | `72hh-3qpy` | Managed money |
| WTI crude | Disaggregated | `72hh-3qpy` | Managed money |

Financial futures use the Traders in Financial Futures report; physical
commodities use the disaggregated report. Contract market codes must be resolved
against the live API during implementation rather than assumed.

## Metrics

Six. Each is a declaration in a registry, not a bespoke code path.

| # | Metric | Definition | Interpretation |
|---|---|---|---|
| 1 | Stock–bond regime | 60d Pearson correlation of `WILL5000IND` daily return vs `DGS10` daily *yield change*; percentile vs all 60d windows over the full common history of the two series | Positive means a growth-driven tape and bonds not hedging equities; negative means rate-driven |
| 2 | Credit vs vol divergence | pctile(`BAMLH0A0HYM2`, 5y) − pctile(`VIXCLS`, 5y) | Positive means credit is more stressed than equity vol; the two markets disagree and one is wrong |
| 3 | Cross-asset co-movement | Mean pairwise absolute 60d correlation across {equity, `DGS10`, `DTWEXBGS`, `BAMLH0A0HYM2`, `DCOILWTICO`, `VIXCLS`}, percentiled | High means one macro factor drives everything; low means idiosyncratic stories |

**Differencing rule, applied everywhere.** Price-like series (`WILL5000IND`,
`DTWEXBGS`, `DCOILWTICO`) are converted to daily log returns. Rate-, spread- and
vol-like series (`DGS10`, `DGS2`, `BAMLH0A0HYM2`, `BAMLC0A0CM`, `VIXCLS`) are
converted to daily first differences, in their native units — basis points for
yields and spreads, vol points for VIX. This is stated because mixing the two
silently changes every correlation in metrics 1 and 3, and because a first
difference in basis points is directly readable where a percent change in a
yield is not. Series are aligned on the intersection of available dates;
holidays and publication gaps are dropped, never forward-filled, since a
forward-filled value injects a false zero return.
| 4 | Positioning percentile | Net position (long − short) per contract, percentile rank over trailing 3y | Crowding, in the conventional CoT-index form |
| 5 | Positioning–price divergence | 3m price percentile vs 3y positioning percentile; flagged when they disagree beyond a threshold | A rally without sponsorship, or a selloff without capitulation |
| 6 | Anomaly ranker | \|percentile − 50\| descending, top 5 across all registered metrics | The front page |

Metric 1 correlates equity returns against **yield changes**, not a synthetic
bond price return. Converting a yield series to a price return requires a
duration assumption — an invisible modeling choice inside a headline number,
which violates the explainability constraint. Stated as yield changes the sign
is unambiguous and the tile explains itself.

Metric 5 is given its own block in the layout rather than sixth position in a
grid. Under the front-office lens it is the most important thing in the system:
the only tile that is implicitly a trade rather than a description.

The divergence threshold in metric 5 is a judgment call. Initial value: flag
when the two percentiles differ by more than 50 points. To be revisited once
there is enough rendered history to see how often it fires.

## Architecture

Five modules, each testable in isolation.

```
sources/   fetch only, no transformation   (fred.py, cftc.py)
metrics/   pure functions + registry
render/    percentile strips, sparklines, page assembly
tests/
.github/workflows/daily.yml
```

**`sources/`** — each module exposes `fetch(series_id, start, end) -> DataFrame[obs_date, value]`
plus static metadata (cadence, expected publication time, units). No
transformation happens here. If a number is changed, it is changed in `metrics/`
where it is unit-testable.

**`metrics/`** — a registry. Each metric declares:

```
name, inputs, window, context_window, fn, interpretation, direction
```

`fn` is pure: frames in, series out, no I/O. The anomaly ranker iterates the
registry generically and never knows what any individual metric is, so adding a
metric is a declaration rather than an edit in several places. `interpretation`
being a required field is what makes the explainability constraint structural.

The registry is more ceremony than six plain functions would be. It is justified
by v2, where the metric count roughly triples, and by the structural enforcement
of `interpretation`.

**Daily flow.** Fetch full history from both sources, compute all metrics,
render static HTML to `dist/`, deploy. No incremental computation — the dataset
is small enough that full recompute is sub-second, and incremental updating
would buy nothing while introducing a genuinely unpleasant class of stale-cache
bugs.

Because the run is stateless and refetches full history, a missed or failed run
costs nothing. The next run is complete. There is no backfill logic and nothing
to repair.

## UI/UX

One page. No navigation, no tabs, no interactivity beyond source links. A brief
is read top to bottom, once.

```
  20 Sep 2026                          sources ok · FRED 08:12 · CFTC Fri

  WHAT'S UNUSUAL TODAY
  1. Stock–bond correlation 60d at +0.41 — 94th pct since 1971. Bonds are not hedging.
  2. Lev funds net long ES 91st pct (3y) while price sits at 3m lows.
  ...top 5, one sentence each, number and percentile inline

  SETUP
  [positioning–price divergence, its own block]

  ───────────────────────────────────────────────
  [metric tiles: dense grid, single column on phone]
     value · percentile strip · sparkline · interpretation · as of / source
```

**Percentiles render as a mark on a distribution strip**, not as a bare number.
"88th percentile" is abstract; a mark sitting in the right tail is immediate.

Typographic and calm. No gauges, no red/amber/green, no card shadows, no chrome
— that visual language reads as risk reporting, which is the signal the author
is moving away from. Every tile always shows its own `as_of` and source.
Sparklines are hand-rolled inline SVG; a charting library for six sparklines
would be unjustified weight. CSS grid collapsing to a single column on phone
width. Light and dark via `prefers-color-scheme`.

Each tile states its own context window explicitly and truthfully ("94th pct
since 1971"), derived from the data actually loaded rather than hardcoded. The
layout sketch above is illustrative; real start dates are whatever the verified
series return.

The `dataviz` skill is to be loaded before any chart or sparkline code is
written.

## Failure and staleness

Mostly free, because Cloudflare Pages retains the last successful deployment.

- A failed build leaves yesterday's site up and fails the Action loudly by email.
- A failed series renders its own tile as `unavailable — <source> <series> fetch
  failed`. Never a silent blank, and never a stale number presented as fresh.
- Any tile whose input is older than its expected cadence is visibly marked
  stale.
- A one-line source header shows last successful fetch per source.

No log page, no status page. Local runs write `run.log`, gitignored.

## Testing

TDD. Metrics are pure functions, so tests are cheap and precise.

- Unit tests per metric on synthetic inputs with hand-computed expected answers.
- One golden test over a small frozen real slice, so a refactor cannot silently
  change a displayed number.
- Source fetchers tested against recorded JSON fixtures, never live APIs.
- One manual live smoke test asserting response schema per source.

No integration harness.

## Deployment

- **Code repository: public.** Resume-linkable. Code, tests, README, workflow.
  No data, no notebooks, no scratch files.
- **Rendered output and data: never in the public repository.** Built in CI,
  deployed directly, discarded.
- **Site: Cloudflare Pages, gated by Cloudflare Access** (free, up to 50 users;
  the only free host that is also private). Free `*.pages.dev` URL, no custom
  domain.
- **Schedule: GitHub Actions cron, daily.** FRED key as an Actions secret.
- The pipeline emits a plain `dist/` folder, so the host is replaceable in
  minutes. Netlify is the fallback if Cloudflare proves irritating.

Total cost: $0.

Note: workflow run logs are public on a public repository. Secrets are masked,
and nothing sensitive is otherwise logged, but this is a known and accepted
property.

The README covers what the brief computes, why these metrics, why explainable
over sophisticated, one screenshot, and how to run locally. That reasoning is
the portfolio artifact — more so than the live site.

## v2 backlog

Not in scope. Recorded so it is not rediscovered.

1. View log with scoring — dated views and reasoning, calibration over time.
   Worker + D1.
2. Plumbing and liquidity family — net liquidity, SOFR–EFFR spread, SOFR tail
   percentiles, auction tails, quarter-end turns.
3. Curve and volatility structure families.
4. The research harness — purged CV, deflated Sharpe. Would reuse this
   ingestion layer and is the only consumer that would justify vintage storage.

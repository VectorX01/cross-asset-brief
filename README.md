# Cross-asset daily brief

A once-daily macro brief that surfaces what is statistically unusual today
rather than what the levels are. Nine metrics, built from two public
sources — FRED and the CFTC Commitments of Traders — rendered to a single
static HTML page with no backend and no client-side JavaScript.

![Screenshot of the rendered brief](docs/img/screenshot.png)

## Why these metrics

Every tile has to earn its place by showing something a consumer finance app
cannot. A level or a price fails that test; a percentile, a positioning
extreme, or a cross-asset relationship passes it.

| Metric | Definition |
|---|---|
| Nasdaq vs 10y regime | 60-day rolling correlation of Nasdaq Composite log returns vs 10y Treasury yield changes, percentiled over the full common history |
| Credit vs vol divergence | 5y percentile of the Baa corporate spread minus 5y percentile of the VIX |
| Cross-asset co-movement | Mean pairwise absolute 60d correlation across equity, 10y yield, dollar, credit, crude and VIX |
| Positioning (×5) | Net speculative position per contract, percentiled over 3 years of weekly CoT reports. The category follows the report: **leveraged funds** for E-mini S&P 500, 10y Treasury note and US Dollar Index (Traders in Financial Futures), **managed money** for gold and WTI crude (disaggregated). The two are not interchangeable, and each tile names which one it is showing |
| Positioning-price divergence | 3y leveraged-fund positioning percentile minus 3-month price percentile, for E-mini S&P 500 |
| What's unusual today | The top 5 of all 9 tiles above, ranked by distance from each tile's own 50th percentile |

Two substitutions from the original plan, forced by data availability rather
than choice:

- **Equity is the Nasdaq Composite, not a broader index.** FRED discontinued
  its Wilshire 5000 series entirely, and its replacements — the S&P 500 and
  Dow — are capped to ten years of history by licensing. Ten years would
  have left the regime tile blind to the pre-2020 era it exists to compare
  against, when stocks and bond yields still moved the other way. The S&P
  500 is kept as a second, separate series (`SP500`) purely to pair with the
  E-mini S&P divergence tile, where ten years of daily prices is ample for a
  three-month percentile — a different metric with a different history
  requirement.
- **Credit is the Baa spread (`BAA10Y`), not a high-yield OAS series.** The
  ICE-sourced OAS series FRED carries are now capped to three years of
  history, which cannot support the five-year stress window the divergence
  metric needs. `BAA10Y` runs back to 1986.

Both tiles are named for what they actually measure — "Nasdaq vs 10y regime"
rather than a generic "stock-bond regime" — instead of pretending the
substitution didn't happen.

CFTC also renamed four of the five tracked contracts' `market_and_exchange_names`
on 2022-02-08. Each is spliced across the rename into one continuous series;
gold, never renamed, holds all 1,058 reports back to 2006 and served as the
check that the splice lines up — the pre- and post-rename halves plus gold's
count matched exactly, with no gap and no overlap. The fetch raises if a
splice ever produces an overlapping report date, rather than silently
double-counting a week.

Positioning-price divergence and the cross-asset comovement tile flag
notability by **percentile**, not a raw threshold: a symmetric band
(`DIVERGENCE_PCTILE = 90`) on the divergence metric's *own* percentile
history, because a threshold on raw percentile-point magnitude would compare
unlike things. When a tile sits in the middle of its own history, its
sentence still states the fact — "62nd percentile of its own history" — it
never claims the reading is unremarkable. The percentile carries the
judgment; the prose only ever states what happened.

## Why explainable over sophisticated

No metric in this system has a fitted parameter. Correlations, percentile
ranks and threshold rules only. Every metric's `interpret` function is a
required field of its registry entry, not optional text bolted on later —
a metric that cannot state its meaning in one sentence cannot be registered.

PCA was considered for cross-asset co-movement and rejected: rolling
loadings flip sign, the rotation needs hand-waving, and "percent variance
explained today" is undefined without a window. Mean pairwise absolute
correlation answers the same question in one sentence and is what ships.

Z-scores were rejected everywhere in favor of percentile rank, which
survives fat tails, needs no stationarity assumption the author can verify
at a glance, and explains itself. Percentile is the single vocabulary of
the entire page, which is also what makes it legitimate to rank nine
unrelated metrics against each other in "what's unusual today": distance
from the 50th percentile is comparable across tiles in a way `|z|` would
not be.

## Staleness and failure handling

A source that fails degrades the page rather than blanking it: `load_levels`
catches per-series fetch errors and the affected tiles render
`"unavailable — <reason>"` instead of taking the whole build down. A stale
tile still renders — with an underline — rather than disappearing.

Staleness tolerance is per-series, not a single global cutoff, because
publication lag is a property of each series, not of the metrics that
happen to consume it. Most FRED series get a 5-day gate; the broad dollar
index (`DTWEXBGS`) publishes with an observed ~9-day lag and gets 12 days,
and WTI crude (`DCOILWTICO`) publishes ~5 days late and gets 8. CFTC data is
weekly and already several days old on arrival, so any metric with a CFTC
input gets at least a 12-day gate. A metric's overall gate is the loosest
tolerance among all of its inputs — it is only as fresh as its
slowest-publishing source.

## Running it

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
export FRED_API_KEY=<key from fred.stlouisfed.org>
.venv/bin/pytest -W error
.venv/bin/python -m brief.cli build   # writes dist/index.html
```

`scripts/smoke.py` checks every configured series and contract against the
live APIs. It is deliberately excluded from CI — it exists to validate ids,
not to run daily.

## Deployment

The page is meant to run on a schedule via GitHub Actions and deploy to
Cloudflare Pages (`.github/workflows/daily.yml`): tests run before the
build, so a broken metric never reaches the live site. Setting up the
Cloudflare project, GitHub secrets and access gate is a one-time, one-person
task — see [`docs/DEPLOY.md`](docs/DEPLOY.md).

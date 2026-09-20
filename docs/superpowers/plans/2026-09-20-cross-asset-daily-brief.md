# Cross-Asset Daily Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A once-daily static cross-asset macro brief that surfaces what is statistically unusual today, built from FRED and CFTC data, deployed free and privately.

**Architecture:** A stateless daily pipeline. Fetch full history from two public APIs, compute six metrics as pure functions registered in a metric registry, render one static HTML page to `dist/`, deploy. No database, no persistent state, no incremental computation — a missed run costs nothing because the next run refetches everything.

**Tech Stack:** Python 3.12, pandas, requests, Jinja2, pytest. GitHub Actions for scheduling, Cloudflare Pages + Access for hosting.

**Spec:** `docs/superpowers/specs/2026-09-20-market-brief-design.md`

## Global Constraints

Every task's requirements implicitly include these. They come from the spec.

- Python 3.12. pandas >= 2.0 (`Rolling.rank` is required and was added in 1.4).
- **No fitted parameters anywhere.** Correlations, percentile ranks, threshold rules only. No PCA, no regression, no GARCH, no curve fitting.
- **Percentile is the only vocabulary.** No z-scores. One percentile definition is used everywhere: `(rank - 1) / (n - 1) * 100`, average method for ties.
- **Differencing rule.** Price-like series (`WILL5000IND`, `DTWEXBGS`, `DCOILWTICO`) become daily log returns. Rate-like series (`DGS10`, `DGS2`, `BAMLH0A0HYM2`, `BAMLC0A0CM`, `VIXCLS`) become daily first differences in native units.
- **Never forward-fill.** Series align on the intersection of dates. A forward-filled value injects a false zero change and drags every correlation toward zero.
- **Every metric must supply an `interpret` function.** Registration fails without one. This is the explainability constraint made structural.
- **No data files in the repository.** No CSV, no Parquet, no JSON output, no notebooks. `dist/` and `run.log` are gitignored. Test fixtures are the sole exception and must be small.
- Build output is a plain `dist/` folder so the host stays replaceable.
- No gauges, no red/amber/green, no card shadows. That visual language reads as risk reporting.

---

## File Structure

```
pyproject.toml
.gitignore
README.md
src/brief/
  config.py              # series + contract definitions, windows
  transforms.py          # differencing, alignment, percentile, correlation
  sources/fred.py        # FRED fetch + pure parser
  sources/cftc.py        # CFTC fetch + pure parser
  metrics/registry.py    # Metric dataclass, register(), REGISTRY
  metrics/cross_asset.py # metrics 1-3
  metrics/positioning.py # metrics 4-5
  rank.py                # anomaly ranker (metric 6)
  render/svg.py          # percentile strip, sparkline
  render/page.py         # payload -> HTML
  render/template.html   # Jinja2 template
  pipeline.py            # fetch -> compute -> payload
  cli.py                 # `python -m brief.cli build`
tests/
  fixtures/              # recorded API JSON, small
  test_transforms.py
  test_sources_fred.py
  test_sources_cftc.py
  test_metrics_cross_asset.py
  test_metrics_positioning.py
  test_rank.py
  test_render.py
  test_golden.py
scripts/smoke.py         # manual live API check, not run in CI
.github/workflows/daily.yml
```

Split by responsibility. `sources/` does I/O and nothing else; every module under `metrics/` is pure and therefore trivially testable.

---

## Task 1: Scaffold and transforms

The pure numerical core. No network, no I/O. Everything downstream depends on these four functions being right.

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/brief/__init__.py`, `src/brief/transforms.py`
- Test: `tests/test_transforms.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `to_change(s: pd.Series, kind: str) -> pd.Series`; `align(*series: pd.Series) -> pd.DataFrame`; `percentile_rank(s: pd.Series, window: int | None = None) -> float`; `rolling_percentile(s: pd.Series, window: int) -> pd.Series`; `rolling_corr(a: pd.Series, b: pd.Series, window: int) -> pd.Series`; `mean_abs_pairwise_corr(df: pd.DataFrame, window: int) -> pd.Series`. Constants `PRICE_LIKE = "price"`, `RATE_LIKE = "rate"`.

- [ ] **Step 1: Create the project scaffold**

`pyproject.toml`:

```toml
[project]
name = "brief"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pandas>=2.0",
    "requests>=2.31",
    "jinja2>=3.1",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:

```
dist/
run.log
__pycache__/
*.egg-info/
.venv/
.env
```

Then:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
mkdir -p src/brief tests
touch src/brief/__init__.py
```

- [ ] **Step 2: Write the failing tests**

`tests/test_transforms.py`:

```python
import numpy as np
import pandas as pd
import pytest

from brief.transforms import (
    PRICE_LIKE,
    RATE_LIKE,
    align,
    mean_abs_pairwise_corr,
    percentile_rank,
    rolling_corr,
    rolling_percentile,
    to_change,
)


def dates(n, start="2020-01-01"):
    return pd.bdate_range(start, periods=n)


def test_price_like_becomes_log_return():
    s = pd.Series([100.0, 110.0], index=dates(2))
    out = to_change(s, PRICE_LIKE)
    assert len(out) == 1
    assert out.iloc[0] == pytest.approx(np.log(1.1))


def test_rate_like_becomes_first_difference_in_native_units():
    s = pd.Series([4.00, 4.07], index=dates(2))
    out = to_change(s, RATE_LIKE)
    assert out.iloc[0] == pytest.approx(0.07)


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        to_change(pd.Series([1.0, 2.0], index=dates(2)), "percent")


def test_align_intersects_dates_and_never_fills():
    a = pd.Series([1.0, 2.0, 3.0], index=dates(3)).rename("a")
    b = pd.Series([1.0, 3.0], index=[dates(3)[0], dates(3)[2]]).rename("b")
    out = align(a, b)
    assert list(out.index) == [dates(3)[0], dates(3)[2]]
    assert out.shape == (2, 2)


def test_percentile_rank_is_zero_at_minimum_and_hundred_at_maximum():
    rising = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=dates(5))
    assert percentile_rank(rising) == pytest.approx(100.0)
    assert percentile_rank(rising.iloc[::-1]) == pytest.approx(0.0)


def test_percentile_rank_is_midpoint_in_the_middle():
    s = pd.Series([1.0, 2.0, 4.0, 5.0, 3.0], index=dates(5))
    assert percentile_rank(s) == pytest.approx(50.0)


def test_percentile_rank_honours_the_trailing_window():
    s = pd.Series([100.0, 1.0, 2.0, 3.0], index=dates(4))
    assert percentile_rank(s, window=3) == pytest.approx(100.0)
    assert percentile_rank(s) == pytest.approx(66.6666, abs=1e-3)


def test_percentile_rank_needs_two_points():
    assert np.isnan(percentile_rank(pd.Series([1.0], index=dates(1))))


def test_rolling_percentile_matches_scalar_percentile_rank():
    s = pd.Series([5.0, 1.0, 2.0, 4.0, 3.0], index=dates(5))
    rolled = rolling_percentile(s, window=3)
    assert rolled.iloc[-1] == pytest.approx(percentile_rank(s, window=3))
    assert len(rolled) == 3


def test_rolling_corr_of_identical_series_is_one():
    s = pd.Series(np.arange(10, dtype=float) % 4, index=dates(10))
    out = rolling_corr(s, s, window=5)
    assert out.iloc[-1] == pytest.approx(1.0)


def test_mean_abs_pairwise_corr_ignores_the_diagonal():
    rng = np.random.default_rng(0)
    base = pd.Series(rng.normal(size=60), index=dates(60))
    df = pd.DataFrame({"a": base, "b": -base, "c": base})
    out = mean_abs_pairwise_corr(df, window=30)
    assert out.iloc[-1] == pytest.approx(1.0)
    assert len(out) == 31
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_transforms.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brief.transforms'`

- [ ] **Step 4: Implement `transforms.py`**

`src/brief/transforms.py`:

```python
"""Pure numerical transforms. No I/O, no state, no fitted parameters."""

import numpy as np
import pandas as pd

PRICE_LIKE = "price"
RATE_LIKE = "rate"


def to_change(s: pd.Series, kind: str) -> pd.Series:
    """Convert a level series to its daily change.

    Price-like series become log returns; rate-like series become first
    differences in their native units (basis points for yields and spreads,
    vol points for VIX). Mixing the two silently changes every correlation.
    """
    s = s.dropna().sort_index()
    if kind == PRICE_LIKE:
        return np.log(s / s.shift(1)).dropna()
    if kind == RATE_LIKE:
        return s.diff().dropna()
    raise ValueError(f"unknown series kind: {kind!r}")


def align(*series: pd.Series) -> pd.DataFrame:
    """Inner-join series on date.

    Never forward-fills: a filled value injects a false zero change and drags
    correlations toward zero on every holiday and publication gap.
    """
    return pd.concat(series, axis=1, join="inner").dropna()


def percentile_rank(s: pd.Series, window: int | None = None) -> float:
    """Percentile rank (0-100) of the last value within its trailing window.

    Minimum scores 0, maximum scores 100. Ties take the average rank.
    """
    s = s.dropna()
    if window is not None:
        s = s.iloc[-window:]
    n = len(s)
    if n < 2:
        return float("nan")
    rank = s.rank(method="average").iloc[-1]
    return float((rank - 1) / (n - 1) * 100)


def rolling_percentile(s: pd.Series, window: int) -> pd.Series:
    """percentile_rank evaluated at every date over a trailing window."""
    s = s.dropna()
    rank = s.rolling(window).rank(method="average")
    return ((rank - 1) / (window - 1) * 100).dropna()


def rolling_corr(a: pd.Series, b: pd.Series, window: int) -> pd.Series:
    """Rolling Pearson correlation of two change series."""
    df = align(a.rename("a"), b.rename("b"))
    return df["a"].rolling(window).corr(df["b"]).dropna()


def mean_abs_pairwise_corr(df: pd.DataFrame, window: int) -> pd.Series:
    """Mean absolute pairwise correlation across every column pair.

    High means one macro factor is driving everything; low means the assets
    are telling unrelated stories.
    """
    n = df.shape[1]
    corr = df.rolling(window).corr()
    abs_sum = corr.abs().groupby(level=0).sum().sum(axis=1)
    complete = corr.notna().groupby(level=0).sum().sum(axis=1) == n * n
    out = (abs_sum - n) / (n * (n - 1))
    return out.where(complete).dropna()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_transforms.py -v`
Expected: PASS, 11 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore src/brief tests/test_transforms.py
git commit -m "feat: add pure numerical transforms with percentile and correlation primitives"
```

---

## Task 2: FRED source

Fetching is separated from parsing so the parser is testable against a fixture and never touches the network.

**Files:**
- Create: `src/brief/config.py`, `src/brief/sources/__init__.py`, `src/brief/sources/fred.py`, `scripts/smoke.py`, `tests/fixtures/fred_dgs10.json`
- Test: `tests/test_sources_fred.py`

**Interfaces:**
- Consumes: `brief.transforms.PRICE_LIKE`, `RATE_LIKE`.
- Produces: `config.SeriesDef(fred_id, label, kind)`; `config.SERIES: dict[str, SeriesDef]`; `fred.parse_observations(payload: dict) -> pd.Series`; `fred.fetch(series_id: str, api_key: str | None = None) -> pd.Series`; `fred.FredError`.

- [ ] **Step 1: Write `config.py`**

`src/brief/config.py`:

```python
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
```

- [ ] **Step 2: Record a fixture from the live API**

Get a free key at `https://fred.stlouisfed.org/docs/api/api_key.html`, then:

```bash
mkdir -p tests/fixtures scripts src/brief/sources
touch src/brief/sources/__init__.py
export FRED_API_KEY=<your key>
curl -s "https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key=$FRED_API_KEY&file_type=json&observation_start=2024-01-01&observation_end=2024-01-31" \
  > tests/fixtures/fred_dgs10.json
head -c 400 tests/fixtures/fred_dgs10.json
```

The fixture must contain at least one observation whose `value` is `"."` — FRED's missing-value marker, which appears on market holidays. January contains New Year's Day and MLK Day, so this should hold. If it does not, widen the date range until it does. Verify:

```bash
grep -c '"\."' tests/fixtures/fred_dgs10.json
```

Expected: at least 1.

- [ ] **Step 3: Verify every configured series id actually resolves**

```bash
for s in WILL5000IND DGS10 DGS2 DTWEXBGS BAMLH0A0HYM2 BAMLC0A0CM VIXCLS DCOILWTICO; do
  n=$(curl -s "https://api.stlouisfed.org/fred/series/observations?series_id=$s&api_key=$FRED_API_KEY&file_type=json" | python3 -c "import sys,json; d=json.load(sys.stdin); o=d.get('observations',[]); print(len(o), o[0]['date'] if o else 'NONE')")
  echo "$s $n"
done
```

Expected: every series returns a non-zero count and a start date. Decision rule: if any id 404s or returns zero observations, find its replacement on `https://fred.stlouisfed.org` and update `SERIES` in `config.py` before continuing. Record each start date in the commit message — these determine the honest context window each tile can claim.

- [ ] **Step 4: Write the failing tests**

`tests/test_sources_fred.py`:

```python
import json
from pathlib import Path

import pandas as pd
import pytest

from brief.sources.fred import FredError, fetch, parse_observations

FIXTURE = Path(__file__).parent / "fixtures" / "fred_dgs10.json"


def test_parse_returns_a_sorted_float_series():
    payload = json.loads(FIXTURE.read_text())
    s = parse_observations(payload)
    assert isinstance(s, pd.Series)
    assert s.dtype == float
    assert isinstance(s.index, pd.DatetimeIndex)
    assert s.index.is_monotonic_increasing


def test_parse_drops_fred_missing_value_marker():
    payload = json.loads(FIXTURE.read_text())
    raw = payload["observations"]
    assert any(o["value"] == "." for o in raw), "fixture must contain a holiday"
    s = parse_observations(payload)
    assert len(s) < len(raw)
    assert not s.isna().any()


def test_parse_rejects_a_payload_with_no_observations_key():
    with pytest.raises(FredError):
        parse_observations({"error_message": "Bad Request."})


def test_fetch_requires_an_api_key(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(FredError, match="FRED_API_KEY"):
        fetch("DGS10")
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_sources_fred.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brief.sources.fred'`

- [ ] **Step 6: Implement `fred.py`**

`src/brief/sources/fred.py`:

```python
"""FRED fetching. I/O only — no transformation happens here."""

import os

import pandas as pd
import requests

BASE = "https://api.stlouisfed.org/fred/series/observations"
TIMEOUT = 30


class FredError(RuntimeError):
    """A FRED request or payload was unusable."""


def parse_observations(payload: dict) -> pd.Series:
    """Turn a FRED observations payload into a clean float series.

    FRED marks missing values with "." on market holidays; those rows are
    dropped rather than filled.
    """
    if "observations" not in payload:
        raise FredError(f"no observations in payload: {payload}")
    dates, values = [], []
    for obs in payload["observations"]:
        if obs["value"] == ".":
            continue
        dates.append(pd.Timestamp(obs["date"]))
        values.append(float(obs["value"]))
    return pd.Series(values, index=pd.DatetimeIndex(dates), name="value").sort_index()


def fetch(series_id: str, api_key: str | None = None) -> pd.Series:
    """Fetch a series' full history. One call returns everything."""
    key = api_key or os.environ.get("FRED_API_KEY")
    if not key:
        raise FredError("FRED_API_KEY is not set")
    params = {"series_id": series_id, "api_key": key, "file_type": "json"}
    response = requests.get(BASE, params=params, timeout=TIMEOUT)
    if response.status_code != 200:
        raise FredError(f"{series_id}: HTTP {response.status_code} {response.text[:200]}")
    return parse_observations(response.json())
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_sources_fred.py -v`
Expected: PASS, 4 passed

- [ ] **Step 8: Write the manual smoke script**

`scripts/smoke.py` — never run in CI; it hits the live APIs.

```python
"""Manual live check. Run: .venv/bin/python scripts/smoke.py"""

from brief.config import SERIES
from brief.sources.fred import fetch

for key, definition in SERIES.items():
    series = fetch(definition.fred_id)
    print(f"{key:8} {definition.fred_id:16} {len(series):>6} obs  {series.index[0].date()} -> {series.index[-1].date()}")
```

Run it: `.venv/bin/python scripts/smoke.py`
Expected: eight lines, each with a non-zero observation count.

- [ ] **Step 9: Commit**

```bash
git add src/brief/config.py src/brief/sources tests/test_sources_fred.py tests/fixtures/fred_dgs10.json scripts/smoke.py
git commit -m "feat: add FRED source with pure parser and verified series ids"
```

---

## Task 3: Metric registry and metric 1

The registry is what makes `interpret` mandatory. Metric 1 is the vertical slice's first real number.

**Files:**
- Create: `src/brief/metrics/__init__.py`, `src/brief/metrics/registry.py`, `src/brief/metrics/cross_asset.py`
- Test: `tests/test_metrics_cross_asset.py`

**Interfaces:**
- Consumes: `transforms.*`, `config.SERIES`, `config.CORR_WINDOW`.
- Produces: `registry.Metric` (fields `name`, `title`, `inputs`, `context_window`, `fn`, `interpret`, `unit`); `registry.register(metric) -> Metric`; `registry.REGISTRY: dict[str, Metric]`; `cross_asset.stock_bond_regime` registered under name `"stock_bond"`. `fn` has signature `(levels: dict[str, pd.Series]) -> pd.Series`; `interpret` has signature `(value: float, pctile: float) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_metrics_cross_asset.py`:

```python
import numpy as np
import pandas as pd
import pytest

from brief.metrics import cross_asset  # noqa: F401  (registers the metrics)
from brief.metrics.registry import REGISTRY, Metric, register


def dates(n):
    return pd.bdate_range("2015-01-01", periods=n)


def test_register_rejects_a_metric_without_an_interpretation():
    with pytest.raises(TypeError):
        Metric(
            name="x",
            title="X",
            inputs=("equity",),
            context_window=None,
            fn=lambda levels: pd.Series(dtype=float),
            unit="",
        )


def test_register_rejects_a_duplicate_name():
    metric = REGISTRY["stock_bond"]
    with pytest.raises(ValueError, match="duplicate"):
        register(metric)


def test_stock_bond_is_positive_when_equities_and_yields_move_together():
    rng = np.random.default_rng(0)
    shock = rng.normal(size=200)
    equity = pd.Series(100 * np.exp(np.cumsum(shock * 0.01)), index=dates(200))
    yields = pd.Series(4.0 + np.cumsum(shock * 0.02), index=dates(200))
    out = REGISTRY["stock_bond"].fn({"equity": equity, "ust10": yields})
    assert out.iloc[-1] > 0.9


def test_stock_bond_is_negative_when_they_move_inversely():
    rng = np.random.default_rng(1)
    shock = rng.normal(size=200)
    equity = pd.Series(100 * np.exp(np.cumsum(shock * 0.01)), index=dates(200))
    yields = pd.Series(4.0 - np.cumsum(shock * 0.02), index=dates(200))
    out = REGISTRY["stock_bond"].fn({"equity": equity, "ust10": yields})
    assert out.iloc[-1] < -0.9


def test_stock_bond_interpretation_names_the_regime():
    positive = REGISTRY["stock_bond"].interpret(0.41, 94.0)
    negative = REGISTRY["stock_bond"].interpret(-0.55, 6.0)
    assert "not hedging" in positive
    assert "hedging" in negative and "not hedging" not in negative
    assert "+0.41" in positive
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_metrics_cross_asset.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brief.metrics'`

- [ ] **Step 3: Implement the registry**

```bash
mkdir -p src/brief/metrics && touch src/brief/metrics/__init__.py
```

`src/brief/metrics/registry.py`:

```python
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


REGISTRY: dict[str, Metric] = {}


def register(metric: Metric) -> Metric:
    if metric.name in REGISTRY:
        raise ValueError(f"duplicate metric name: {metric.name}")
    REGISTRY[metric.name] = metric
    return metric
```

Because `Metric` is a frozen dataclass with no defaults, omitting `interpret` raises `TypeError` at construction — which is what the first test asserts.

- [ ] **Step 4: Implement metric 1**

`src/brief/metrics/cross_asset.py`:

```python
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
            f"Equities and 10y yields are moving together ({value:+.2f}) — "
            "a growth-driven tape, and bonds are not hedging equities."
        )
    return (
        f"Equities and 10y yields are moving inversely ({value:+.2f}) — "
        "a rate-driven tape, and bonds are hedging equities."
    )


stock_bond_regime = register(
    Metric(
        name="stock_bond",
        title="Stock-bond regime",
        inputs=("equity", "ust10"),
        context_window=None,
        fn=_stock_bond,
        interpret=_interpret_stock_bond,
        unit="corr",
    )
)
```

`context_window=None` means the percentile is taken over the full common history of the two series.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_metrics_cross_asset.py -v`
Expected: PASS, 5 passed

- [ ] **Step 6: Commit**

```bash
git add src/brief/metrics tests/test_metrics_cross_asset.py
git commit -m "feat: add metric registry enforcing interpretations, plus stock-bond regime"
```

---

## Task 4: Pipeline and first render — the vertical slice closes

After this task you can open a real page showing a real number. Everything after widens it.

**Files:**
- Create: `src/brief/pipeline.py`, `src/brief/render/__init__.py`, `src/brief/render/svg.py`, `src/brief/render/template.html`, `src/brief/render/page.py`, `src/brief/cli.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `REGISTRY`, `config.SERIES`, `transforms.percentile_rank`, `sources.fred.fetch`.
- Produces: `pipeline.Tile` (fields `name`, `title`, `value`, `pctile`, `sentence`, `history`, `as_of`, `unit`, `error`, `stale`); `pipeline.build_payload(levels: dict[str, pd.Series]) -> dict`; `pipeline.load_levels() -> dict[str, pd.Series]`; `svg.percentile_strip(pct: float) -> str`; `svg.sparkline(values: list[float]) -> str`; `page.render(payload: dict) -> str`; `cli.main()`.

- [ ] **Step 1: Load the dataviz skill**

Before writing any SVG, run the `dataviz` skill. It is mandatory before the first line of chart code and governs the palette, the sparkline shape, and the strip's axis treatment. Apply its palette guidance to the CSS in `template.html`, and record in the commit message which palette values were used.

- [ ] **Step 2: Write the failing tests**

`tests/test_render.py`:

```python
import numpy as np
import pandas as pd
import pytest

from brief.metrics import cross_asset  # noqa: F401
from brief.pipeline import build_payload
from brief.render.page import render
from brief.render.svg import percentile_strip, sparkline


def synthetic_levels(n=400):
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(7)
    shock = rng.normal(size=n)
    return {
        "equity": pd.Series(100 * np.exp(np.cumsum(shock * 0.01)), index=idx),
        "ust10": pd.Series(4.0 + np.cumsum(shock * 0.02), index=idx),
    }


def test_percentile_strip_places_the_mark_proportionally():
    left = percentile_strip(0.0)
    right = percentile_strip(100.0)
    assert left.startswith("<svg") and right.startswith("<svg")
    assert 'x1="0"' in left
    assert 'x1="160"' in right


def test_sparkline_emits_one_point_per_value():
    out = sparkline([1.0, 2.0, 3.0])
    assert out.count(",") == 3


def test_sparkline_survives_a_flat_series():
    out = sparkline([2.0, 2.0, 2.0])
    assert "<svg" in out
    assert "nan" not in out.lower()


def test_payload_has_one_tile_per_registered_metric():
    payload = build_payload(synthetic_levels())
    assert len(payload["tiles"]) == 1
    tile = payload["tiles"][0]
    assert tile.name == "stock_bond"
    assert -1.0 <= tile.value <= 1.0
    assert 0.0 <= tile.pctile <= 100.0
    assert tile.sentence
    assert tile.error is None


def test_payload_records_an_error_instead_of_raising_on_missing_input():
    payload = build_payload({"equity": synthetic_levels()["equity"]})
    tile = payload["tiles"][0]
    assert tile.value is None
    assert "ust10" in tile.error


def test_render_produces_a_page_containing_the_sentence():
    payload = build_payload(synthetic_levels())
    html = render(payload)
    assert html.startswith("<!doctype html>")
    assert payload["tiles"][0].sentence in html
    assert "viewport" in html


def test_render_shows_the_unavailable_reason_rather_than_a_blank():
    payload = build_payload({"equity": synthetic_levels()["equity"]})
    html = render(payload)
    assert "unavailable" in html
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brief.pipeline'`

- [ ] **Step 4: Implement the pipeline**

`src/brief/pipeline.py`:

```python
"""Fetch, compute, assemble. Stateless: a missed run costs nothing."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from brief.config import SERIES
from brief.metrics.registry import REGISTRY
from brief.sources.fred import fetch
from brief.transforms import percentile_rank

SPARK_POINTS = 120


@dataclass
class Tile:
    name: str
    title: str
    value: float | None
    pctile: float | None
    sentence: str
    history: list[float]
    as_of: str
    unit: str
    error: str | None = None
    stale: bool = False


def load_levels() -> dict[str, pd.Series]:
    """Fetch every configured series' full history."""
    return {key: fetch(definition.fred_id) for key, definition in SERIES.items()}


def _tile_for(metric, levels: dict[str, pd.Series]) -> Tile:
    missing = [name for name in metric.inputs if name not in levels]
    if missing:
        return Tile(
            name=metric.name,
            title=metric.title,
            value=None,
            pctile=None,
            sentence=f"unavailable — missing input {', '.join(missing)}",
            history=[],
            as_of="",
            unit=metric.unit,
            error=f"missing input {', '.join(missing)}",
        )
    try:
        series = metric.fn({name: levels[name] for name in metric.inputs})
    except Exception as exc:  # a broken metric must not take the page down
        return Tile(
            name=metric.name,
            title=metric.title,
            value=None,
            pctile=None,
            sentence=f"unavailable — {exc}",
            history=[],
            as_of="",
            unit=metric.unit,
            error=str(exc),
        )
    value = float(series.iloc[-1])
    pctile = percentile_rank(series, window=metric.context_window)
    return Tile(
        name=metric.name,
        title=metric.title,
        value=value,
        pctile=pctile,
        sentence=metric.interpret(value, pctile),
        history=[float(v) for v in series.iloc[-SPARK_POINTS:]],
        as_of=str(series.index[-1].date()),
        unit=metric.unit,
    )


def build_payload(levels: dict[str, pd.Series]) -> dict:
    tiles = [_tile_for(metric, levels) for metric in REGISTRY.values()]
    return {"date": str(date.today()), "tiles": tiles}
```

- [ ] **Step 5: Implement the SVG helpers**

```bash
mkdir -p src/brief/render && touch src/brief/render/__init__.py
```

`src/brief/render/svg.py`:

```python
"""Hand-rolled inline SVG. Six sparklines do not justify a charting library."""

STRIP_WIDTH = 160
STRIP_HEIGHT = 8
SPARK_WIDTH = 160
SPARK_HEIGHT = 28


def percentile_strip(pct: float) -> str:
    """A mark on a distribution strip. A tail position reads faster than a number."""
    x = round(STRIP_WIDTH * pct / 100)
    return (
        f'<svg class="strip" viewBox="0 0 {STRIP_WIDTH} {STRIP_HEIGHT}" '
        f'width="{STRIP_WIDTH}" height="{STRIP_HEIGHT}" aria-hidden="true">'
        f'<rect x="0" y="3" width="{STRIP_WIDTH}" height="2" class="strip-bg"/>'
        f'<line x1="{x}" y1="0" x2="{x}" y2="{STRIP_HEIGHT}" class="strip-mark"/>'
        "</svg>"
    )


def sparkline(values: list[float]) -> str:
    """A flat series must still render — never emit NaN coordinates."""
    if not values:
        return ""
    low, high = min(values), max(values)
    span = high - low
    step = SPARK_WIDTH / max(len(values) - 1, 1)
    points = []
    for i, v in enumerate(values):
        y = SPARK_HEIGHT / 2 if span == 0 else SPARK_HEIGHT * (1 - (v - low) / span)
        points.append(f"{i * step:.1f},{y:.1f}")
    return (
        f'<svg class="spark" viewBox="0 0 {SPARK_WIDTH} {SPARK_HEIGHT}" '
        f'width="{SPARK_WIDTH}" height="{SPARK_HEIGHT}" aria-hidden="true">'
        f'<polyline points="{" ".join(points)}" fill="none"/>'
        "</svg>"
    )
```

The test counts commas: three values produce three `x,y` pairs, hence three commas.

- [ ] **Step 6: Implement the template and page renderer**

`src/brief/render/template.html` — typographic and calm. No gauges, no traffic lights, no shadows. Substitute the palette values chosen from the dataviz skill in Step 1.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cross-asset brief — {{ payload.date }}</title>
<style>
  :root { --bg:#fbfaf8; --fg:#1a1a1a; --muted:#6b6b6b; --rule:#e2e0dc; --mark:#1a1a1a; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#141414; --fg:#ededed; --muted:#9a9a9a; --rule:#2e2e2e; --mark:#ededed; }
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font:15px/1.5 ui-sans-serif, -apple-system, system-ui, sans-serif; }
  main { max-width: 820px; margin:0 auto; padding: 32px 20px 64px; }
  header { display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap;
           padding-bottom:12px; border-bottom:1px solid var(--rule); }
  h1 { font-size:15px; font-weight:600; margin:0; letter-spacing:0.01em; }
  .meta { color:var(--muted); font-size:13px; }
  h2 { font-size:11px; font-weight:600; letter-spacing:0.09em; text-transform:uppercase;
       color:var(--muted); margin:40px 0 12px; }
  ol { margin:0; padding-left:20px; }
  ol li { margin-bottom:10px; }
  .grid { display:grid; grid-template-columns:repeat(2, 1fr); gap:28px 32px; }
  @media (max-width:640px) { .grid { grid-template-columns:1fr; } }
  .tile { border-top:1px solid var(--rule); padding-top:12px; }
  .tile h3 { font-size:14px; font-weight:600; margin:0 0 6px; }
  .value { font-size:24px; font-variant-numeric:tabular-nums; margin:0; }
  .pct { color:var(--muted); font-size:13px; font-variant-numeric:tabular-nums; }
  .sentence { margin:8px 0 0; }
  .asof { color:var(--muted); font-size:12px; margin-top:8px; }
  .stale { text-decoration:underline dotted; }
  .strip-bg { fill:var(--rule); }
  .strip-mark { stroke:var(--mark); stroke-width:2; }
  .spark polyline { stroke:var(--muted); stroke-width:1.25; }
</style>
</head>
<body>
<main>
  <header>
    <h1>Cross-asset brief</h1>
    <span class="meta">{{ payload.date }}</span>
  </header>

  <h2>Metrics</h2>
  <div class="grid">
  {% for tile in payload.tiles %}
    <section class="tile">
      <h3>{{ tile.title }}</h3>
      {% if tile.error %}
        <p class="sentence">unavailable — {{ tile.error }}</p>
      {% else %}
        <p class="value">{{ "%+.2f"|format(tile.value) }}</p>
        {{ strip(tile.pctile) }}
        <p class="pct">{{ "%.0f"|format(tile.pctile) }}th percentile</p>
        {{ spark(tile.history) }}
        <p class="sentence">{{ tile.sentence }}</p>
        <p class="asof {% if tile.stale %}stale{% endif %}">as of {{ tile.as_of }}</p>
      {% endif %}
    </section>
  {% endfor %}
  </div>
</main>
</body>
</html>
```

`src/brief/render/page.py`:

```python
"""Payload to HTML."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from brief.render.svg import percentile_strip, sparkline

TEMPLATE_DIR = Path(__file__).parent


def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["strip"] = lambda pct: _markup(percentile_strip(pct))
    env.globals["spark"] = lambda values: _markup(sparkline(values))
    return env


def _markup(svg: str):
    from markupsafe import Markup

    return Markup(svg)


def render(payload: dict) -> str:
    return _environment().get_template("template.html").render(payload=payload)
```

`markupsafe` ships with Jinja2, so this adds no dependency. The SVG helpers emit trusted markup built from floats, never from fetched data, so marking it safe is sound.

- [ ] **Step 7: Implement the CLI**

`src/brief/cli.py`:

```python
"""Build the static site. `python -m brief.cli build`"""

import sys
from pathlib import Path

from brief.metrics import cross_asset  # noqa: F401  (registers metrics)
from brief.pipeline import build_payload, load_levels
from brief.render.page import render

DIST = Path("dist")


def main() -> int:
    payload = build_payload(load_levels())
    DIST.mkdir(exist_ok=True)
    (DIST / "index.html").write_text(render(payload), encoding="utf-8")
    broken = [t.name for t in payload["tiles"] if t.error]
    print(f"built dist/index.html — {len(payload['tiles'])} tiles, {len(broken)} unavailable")
    if broken:
        print(f"unavailable: {', '.join(broken)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

The build does not fail when a tile is unavailable — the page still renders, saying so honestly. Only a total failure fails the build, which leaves yesterday's deployment up.

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/pytest -v`
Expected: PASS, 20 passed

- [ ] **Step 9: Build against live data and look at it**

```bash
export FRED_API_KEY=<your key>
.venv/bin/python -m brief.cli build
open dist/index.html
```

Expected: a page with one tile showing a correlation between -1 and 1, a percentile strip, a sparkline, a sentence, and an as-of date. Check it in a narrow window too — it must collapse to one column below 640px.

- [ ] **Step 10: Commit**

```bash
git add src/brief/pipeline.py src/brief/render src/brief/cli.py tests/test_render.py
git commit -m "feat: close the vertical slice — fetch, compute, render one real tile"
```

---

## Task 5: Metrics 2 and 3

**Files:**
- Modify: `src/brief/metrics/cross_asset.py`
- Test: `tests/test_metrics_cross_asset.py`

**Interfaces:**
- Consumes: `transforms.rolling_percentile`, `transforms.mean_abs_pairwise_corr`, `config.COMOVEMENT_BASKET`, `config.STRESS_WINDOW_YEARS`, `config.TRADING_DAYS_PER_YEAR`.
- Produces: metrics registered under `"credit_vs_vol"` and `"comovement"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_metrics_cross_asset.py`:

```python
def test_credit_vs_vol_is_positive_when_credit_is_the_stressed_one():
    idx = pd.bdate_range("2015-01-01", periods=1400)
    hy = pd.Series(np.linspace(3.0, 9.0, 1400), index=idx)
    vix = pd.Series(np.linspace(30.0, 12.0, 1400), index=idx)
    out = REGISTRY["credit_vs_vol"].fn({"hy": hy, "vix": vix})
    assert out.iloc[-1] > 50


def test_credit_vs_vol_is_negative_when_equity_vol_is_the_stressed_one():
    idx = pd.bdate_range("2015-01-01", periods=1400)
    hy = pd.Series(np.linspace(9.0, 3.0, 1400), index=idx)
    vix = pd.Series(np.linspace(12.0, 30.0, 1400), index=idx)
    out = REGISTRY["credit_vs_vol"].fn({"hy": hy, "vix": vix})
    assert out.iloc[-1] < -50


def test_credit_vs_vol_interpretation_names_the_stressed_market():
    assert "credit" in REGISTRY["credit_vs_vol"].interpret(62.0, 91.0).lower()
    assert "vol" in REGISTRY["credit_vs_vol"].interpret(-62.0, 8.0).lower()


def test_comovement_is_high_when_every_asset_shares_one_driver():
    idx = pd.bdate_range("2015-01-01", periods=300)
    rng = np.random.default_rng(3)
    shock = rng.normal(size=300)
    levels = {
        "equity": pd.Series(100 * np.exp(np.cumsum(shock * 0.01)), index=idx),
        "ust10": pd.Series(4.0 + np.cumsum(shock * 0.02), index=idx),
        "usd": pd.Series(100 * np.exp(np.cumsum(shock * 0.005)), index=idx),
        "hy": pd.Series(4.0 + np.cumsum(shock * 0.01), index=idx),
        "wti": pd.Series(70 * np.exp(np.cumsum(shock * 0.02)), index=idx),
        "vix": pd.Series(18.0 + np.cumsum(shock * 0.05), index=idx),
    }
    out = REGISTRY["comovement"].fn(levels)
    assert out.iloc[-1] > 0.9


def test_comovement_is_low_when_assets_are_independent():
    idx = pd.bdate_range("2015-01-01", periods=300)
    rng = np.random.default_rng(4)
    levels = {
        name: pd.Series(100 + np.cumsum(rng.normal(size=300)), index=idx)
        for name in ("equity", "ust10", "usd", "hy", "wti", "vix")
    }
    out = REGISTRY["comovement"].fn(levels)
    assert out.iloc[-1] < 0.4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_metrics_cross_asset.py -v`
Expected: FAIL — `KeyError: 'credit_vs_vol'`

- [ ] **Step 3: Implement both metrics**

Append to `src/brief/metrics/cross_asset.py`:

```python
from brief.config import (
    COMOVEMENT_BASKET,
    STRESS_WINDOW_YEARS,
    TRADING_DAYS_PER_YEAR,
)
from brief.transforms import align, mean_abs_pairwise_corr, rolling_percentile

STRESS_WINDOW = STRESS_WINDOW_YEARS * TRADING_DAYS_PER_YEAR


def _credit_vs_vol(levels: dict[str, pd.Series]) -> pd.Series:
    hy = rolling_percentile(levels["hy"], STRESS_WINDOW).rename("hy")
    vix = rolling_percentile(levels["vix"], STRESS_WINDOW).rename("vix")
    joined = align(hy, vix)
    return joined["hy"] - joined["vix"]


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
    return f"Mean pairwise correlation {value:.2f} — unremarkable co-movement."


credit_vs_vol = register(
    Metric(
        name="credit_vs_vol",
        title="Credit vs vol divergence",
        inputs=("hy", "vix"),
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_metrics_cross_asset.py -v`
Expected: PASS, 10 passed

- [ ] **Step 5: Rebuild and inspect**

```bash
.venv/bin/python -m brief.cli build && open dist/index.html
```

Expected: three tiles. Confirm none reads `unavailable`.

- [ ] **Step 6: Commit**

```bash
git add src/brief/metrics/cross_asset.py tests/test_metrics_cross_asset.py
git commit -m "feat: add credit-vs-vol divergence and cross-asset co-movement metrics"
```

---

## Task 6: CFTC source

**Files:**
- Create: `src/brief/sources/cftc.py`, `tests/fixtures/cftc_tff.json`, `tests/fixtures/cftc_disagg.json`
- Modify: `src/brief/config.py`, `scripts/smoke.py`
- Test: `tests/test_sources_cftc.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `config.ContractDef(report, market_code, label, price_series)`; `config.CONTRACTS: dict[str, ContractDef]`; `cftc.parse_positions(rows: list[dict], report: str) -> pd.Series`; `cftc.fetch(contract_key: str) -> pd.Series`; `cftc.CftcError`; `cftc.DATASETS: dict[str, str]`; `cftc.FIELDS: dict[str, tuple[str, str]]`.

- [ ] **Step 1: Discover the real field and market names**

Field names must be read from the live API, not assumed. Run:

```bash
curl -s 'https://publicreporting.cftc.gov/resource/gpe5-46if.json?$limit=1' \
  | python3 -m json.tool | head -60
curl -s 'https://publicreporting.cftc.gov/resource/72hh-3qpy.json?$limit=1' \
  | python3 -m json.tool | head -60
```

From the TFF output, identify the report-date field, the market-name field, and the leveraged-funds long and short position fields. From the disaggregated output, identify the managed-money long and short fields. Then find the exact market strings:

```bash
for q in 'E-MINI+S%26P+500' 'UST+10Y' 'USD+INDEX'; do
  curl -s "https://publicreporting.cftc.gov/resource/gpe5-46if.json?\$select=market_and_exchange_names&\$where=market_and_exchange_names%20like%20'%25${q}%25'&\$limit=3" \
    | python3 -m json.tool
done
curl -s "https://publicreporting.cftc.gov/resource/72hh-3qpy.json?\$select=market_and_exchange_names&\$where=market_and_exchange_names%20like%20'%25GOLD%25'&\$limit=3" | python3 -m json.tool
curl -s "https://publicreporting.cftc.gov/resource/72hh-3qpy.json?\$select=market_and_exchange_names&\$where=market_and_exchange_names%20like%20'%25CRUDE%20OIL%25'&\$limit=3" | python3 -m json.tool
```

Decision rule: copy the exact returned strings into `CONTRACTS` below. Do not paraphrase them — Socrata matches literally. If a query returns nothing, widen the `like` pattern until it does.

- [ ] **Step 2: Record fixtures**

```bash
curl -s 'https://publicreporting.cftc.gov/resource/gpe5-46if.json?$limit=20' > tests/fixtures/cftc_tff.json
curl -s 'https://publicreporting.cftc.gov/resource/72hh-3qpy.json?$limit=20' > tests/fixtures/cftc_disagg.json
```

- [ ] **Step 3: Extend `config.py`**

Append to `src/brief/config.py`, substituting the exact market strings from Step 1:

```python
@dataclass(frozen=True)
class ContractDef:
    report: str          # "tff" or "disagg"
    market_code: str     # exact market_and_exchange_names value
    label: str
    price_series: str | None   # key into SERIES, or None if no free daily price


CONTRACTS: dict[str, ContractDef] = {
    "es": ContractDef("tff", "<exact ES string>", "E-mini S&P 500", "equity"),
    "ust10": ContractDef("tff", "<exact UST 10Y string>", "10y Treasury note", "ust10"),
    "dxy": ContractDef("tff", "<exact USD index string>", "US Dollar Index", "usd"),
    "gold": ContractDef("disagg", "<exact gold string>", "Gold", None),
    "wti": ContractDef("disagg", "<exact WTI string>", "WTI crude", "wti"),
}
```

Gold carries `price_series=None`: FRED has no verified free daily gold series, so gold appears in the positioning percentile but is excluded from the divergence metric, which needs a price. This is a deliberate scope decision, not an oversight.

- [ ] **Step 4: Write the failing tests**

`tests/test_sources_cftc.py`:

```python
import json
from pathlib import Path

import pandas as pd
import pytest

from brief.sources.cftc import CftcError, parse_positions

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_tff_returns_net_positions_sorted_by_date():
    rows = json.loads((FIXTURES / "cftc_tff.json").read_text())
    s = parse_positions(rows, "tff")
    assert isinstance(s, pd.Series)
    assert s.index.is_monotonic_increasing
    assert s.dtype == float


def test_parse_disagg_returns_net_positions():
    rows = json.loads((FIXTURES / "cftc_disagg.json").read_text())
    s = parse_positions(rows, "disagg")
    assert len(s) > 0
    assert s.dtype == float


def test_net_position_is_long_minus_short():
    rows = json.loads((FIXTURES / "cftc_tff.json").read_text())
    s = parse_positions(rows, "tff")
    row = rows[0]
    from brief.sources.cftc import FIELDS

    date_field = "report_date_as_yyyy_mm_dd"
    long_field, short_field = FIELDS["tff"]
    expected = float(row[long_field]) - float(row[short_field])
    assert s.loc[pd.Timestamp(row[date_field][:10])] == pytest.approx(expected)


def test_parse_rejects_an_unknown_report():
    with pytest.raises(CftcError):
        parse_positions([], "legacy")


def test_parse_rejects_empty_rows():
    with pytest.raises(CftcError, match="no rows"):
        parse_positions([], "tff")
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_sources_cftc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brief.sources.cftc'`

- [ ] **Step 6: Implement `cftc.py`**

`src/brief/sources/cftc.py`, substituting the field names discovered in Step 1:

```python
"""CFTC Commitments of Traders. No API key required."""

import pandas as pd
import requests

from brief.config import CONTRACTS

BASE = "https://publicreporting.cftc.gov/resource"
TIMEOUT = 60
LIMIT = 50000
DATE_FIELD = "report_date_as_yyyy_mm_dd"
MARKET_FIELD = "market_and_exchange_names"

DATASETS = {"tff": "gpe5-46if", "disagg": "72hh-3qpy"}

# (long field, short field) per report — verified against the live API.
FIELDS = {
    "tff": ("lev_money_positions_long", "lev_money_positions_short"),
    "disagg": ("m_money_positions_long_all", "m_money_positions_short_all"),
}


class CftcError(RuntimeError):
    """A CFTC request or payload was unusable."""


def parse_positions(rows: list[dict], report: str) -> pd.Series:
    """Net position (long minus short) per report date."""
    if report not in FIELDS:
        raise CftcError(f"unknown report: {report!r}")
    if not rows:
        raise CftcError("no rows returned")
    long_field, short_field = FIELDS[report]
    dates, values = [], []
    for row in rows:
        if long_field not in row or short_field not in row:
            continue
        dates.append(pd.Timestamp(row[DATE_FIELD][:10]))
        values.append(float(row[long_field]) - float(row[short_field]))
    if not values:
        raise CftcError(f"no rows carried {long_field}/{short_field}")
    return pd.Series(values, index=pd.DatetimeIndex(dates), name="net").sort_index()


def fetch(contract_key: str) -> pd.Series:
    contract = CONTRACTS[contract_key]
    params = {
        "$limit": LIMIT,
        "$where": f"{MARKET_FIELD}='{contract.market_code}'",
        "$order": f"{DATE_FIELD} ASC",
    }
    url = f"{BASE}/{DATASETS[contract.report]}.json"
    response = requests.get(url, params=params, timeout=TIMEOUT)
    if response.status_code != 200:
        raise CftcError(f"{contract_key}: HTTP {response.status_code} {response.text[:200]}")
    return parse_positions(response.json(), contract.report)
```

If Step 1 showed different field names, correct `FIELDS` here and re-run the tests.

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_sources_cftc.py -v`
Expected: PASS, 5 passed

- [ ] **Step 8: Extend the smoke script and run it**

Append to `scripts/smoke.py`:

```python
from brief.config import CONTRACTS
from brief.sources.cftc import fetch as fetch_cot

for key in CONTRACTS:
    series = fetch_cot(key)
    print(f"{key:8} {len(series):>6} reports  {series.index[0].date()} -> {series.index[-1].date()}")
```

Run: `.venv/bin/python scripts/smoke.py`
Expected: five contract lines, each with several hundred weekly reports. A zero count means the market string in `CONTRACTS` is wrong — return to Step 1.

- [ ] **Step 9: Commit**

```bash
git add src/brief/sources/cftc.py src/brief/config.py tests/test_sources_cftc.py tests/fixtures/cftc_tff.json tests/fixtures/cftc_disagg.json scripts/smoke.py
git commit -m "feat: add CFTC source for TFF and disaggregated net positioning"
```

---

## Task 7: Metrics 4 and 5

Metric 5 is the one the front-office lens promotes: the only tile that is implicitly a trade.

**Files:**
- Create: `src/brief/metrics/positioning.py`
- Modify: `src/brief/pipeline.py`, `src/brief/cli.py`
- Test: `tests/test_metrics_positioning.py`

**Interfaces:**
- Consumes: `config.CONTRACTS`, `config.DIVERGENCE_THRESHOLD`, `transforms.percentile_rank`, `registry.register`.
- Produces: metrics registered as `"pos_<contract_key>"` for each contract, and `"divergence"`. `pipeline.load_levels` extended to include keys `"cot_<contract_key>"`.

- [ ] **Step 1: Write the failing tests**

`tests/test_metrics_positioning.py`:

```python
import numpy as np
import pandas as pd

from brief.metrics import positioning  # noqa: F401
from brief.metrics.registry import REGISTRY


def weekly(n):
    return pd.date_range("2018-01-02", periods=n, freq="W-TUE")


def test_a_positioning_metric_exists_for_every_contract():
    from brief.config import CONTRACTS

    for key in CONTRACTS:
        assert f"pos_{key}" in REGISTRY


def test_positioning_metric_returns_the_net_position_series():
    net = pd.Series(np.arange(200, dtype=float), index=weekly(200))
    out = REGISTRY["pos_es"].fn({"cot_es": net})
    assert out.iloc[-1] == 199.0


def test_positioning_interpretation_calls_out_crowding():
    assert "crowded" in REGISTRY["pos_es"].interpret(120000.0, 96.0).lower()
    assert "crowded" in REGISTRY["pos_es"].interpret(-90000.0, 3.0).lower()
    assert "crowded" not in REGISTRY["pos_es"].interpret(1000.0, 50.0).lower()


def test_divergence_is_positive_when_positioning_is_long_into_weak_price():
    idx = pd.bdate_range("2019-01-01", periods=900)
    price = pd.Series(np.linspace(120.0, 90.0, 900), index=idx)
    net = pd.Series(np.linspace(-50000.0, 90000.0, 200), index=weekly(200))
    out = REGISTRY["divergence"].fn({"cot_es": net, "equity": price})
    assert out.iloc[-1] > 50


def test_divergence_is_negative_when_positioning_is_short_into_strong_price():
    idx = pd.bdate_range("2019-01-01", periods=900)
    price = pd.Series(np.linspace(90.0, 120.0, 900), index=idx)
    net = pd.Series(np.linspace(90000.0, -50000.0, 200), index=weekly(200))
    out = REGISTRY["divergence"].fn({"cot_es": net, "equity": price})
    assert out.iloc[-1] < -50


def test_divergence_interpretation_describes_the_setup():
    assert "sponsorship" in REGISTRY["divergence"].interpret(70.0, 97.0).lower()
    assert "capitulation" in REGISTRY["divergence"].interpret(-70.0, 2.0).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_metrics_positioning.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brief.metrics.positioning'`

- [ ] **Step 3: Implement `positioning.py`**

`src/brief/metrics/positioning.py`:

```python
"""Positioning and flows. CoT is weekly and three days stale on arrival:
it contextualises rather than triggers."""

import pandas as pd

from brief.config import (
    CONTRACTS,
    DIVERGENCE_THRESHOLD,
    POSITIONING_WINDOW_YEARS,
)
from brief.metrics.registry import Metric, register
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
                f"{label}: net {side} {abs(value):,.0f} contracts, {pctile:.0f}th "
                "percentile of three years — a crowded position."
            )
        if pctile <= 10:
            return (
                f"{label}: net {side} {abs(value):,.0f} contracts, {pctile:.0f}th "
                "percentile of three years — a crowded position on the other side."
            )
        return (
            f"{label}: net {side} {abs(value):,.0f} contracts, {pctile:.0f}th "
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
    if value >= DIVERGENCE_THRESHOLD:
        return (
            f"Leveraged funds are {value:.0f} percentile points longer than price "
            "justifies — a rally without sponsorship, vulnerable to long liquidation."
        )
    if value <= -DIVERGENCE_THRESHOLD:
        return (
            f"Leveraged funds are {abs(value):.0f} percentile points shorter than "
            "price justifies — a selloff without capitulation, vulnerable to a squeeze."
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
```

- [ ] **Step 4: Extend the pipeline to load CoT data**

In `src/brief/pipeline.py`, replace `load_levels` with:

```python
def load_levels() -> dict[str, pd.Series]:
    """Fetch every configured series and contract. Full history, every run."""
    from brief.config import CONTRACTS
    from brief.sources.cftc import fetch as fetch_cot

    levels: dict[str, pd.Series] = {}
    for key, definition in SERIES.items():
        levels[key] = fetch(definition.fred_id)
    for key in CONTRACTS:
        levels[f"cot_{key}"] = fetch_cot(key)
    return levels
```

In `src/brief/cli.py`, add the positioning import beside the existing one so the metrics register:

```python
from brief.metrics import cross_asset, positioning  # noqa: F401  (registers metrics)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest -v`
Expected: PASS, all tests

- [ ] **Step 6: Rebuild and inspect**

```bash
.venv/bin/python -m brief.cli build && open dist/index.html
```

Expected: nine tiles (three cross-asset, five positioning, one divergence), none unavailable.

- [ ] **Step 7: Commit**

```bash
git add src/brief/metrics/positioning.py src/brief/pipeline.py src/brief/cli.py tests/test_metrics_positioning.py
git commit -m "feat: add positioning percentiles and positioning-price divergence"
```

---

## Task 8: Anomaly ranker and final page layout

**Files:**
- Create: `src/brief/rank.py`
- Modify: `src/brief/pipeline.py`, `src/brief/render/template.html`
- Test: `tests/test_rank.py`

**Interfaces:**
- Consumes: `pipeline.Tile`.
- Produces: `rank.rank_anomalies(tiles: list[Tile], top: int = 5) -> list[Tile]`; `build_payload` gains keys `"unusual"` (list of Tile) and `"setup"` (Tile or None).

- [ ] **Step 1: Write the failing tests**

`tests/test_rank.py`:

```python
from brief.pipeline import Tile
from brief.rank import rank_anomalies


def tile(name, pctile, error=None):
    return Tile(
        name=name,
        title=name,
        value=0.0 if error is None else None,
        pctile=pctile,
        sentence=name,
        history=[],
        as_of="2026-09-20",
        unit="",
        error=error,
    )


def test_ranks_by_distance_from_the_median():
    ranked = rank_anomalies([tile("a", 50.0), tile("b", 97.0), tile("c", 2.0)])
    assert [t.name for t in ranked] == ["c", "b", "a"]


def test_treats_both_tails_as_equally_unusual():
    ranked = rank_anomalies([tile("high", 95.0), tile("low", 5.0)])
    assert {t.name for t in ranked} == {"high", "low"}


def test_excludes_unavailable_tiles():
    ranked = rank_anomalies([tile("broken", None, error="boom"), tile("ok", 80.0)])
    assert [t.name for t in ranked] == ["ok"]


def test_returns_at_most_the_requested_count():
    tiles = [tile(str(i), float(i)) for i in range(20)]
    assert len(rank_anomalies(tiles, top=5)) == 5


def test_empty_input_is_not_an_error():
    assert rank_anomalies([]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_rank.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brief.rank'`

- [ ] **Step 3: Implement the ranker**

`src/brief/rank.py`:

```python
"""The anomaly ranker.

Ranking heterogeneous metrics against each other is only legitimate because
every metric speaks the same language: a percentile. Distance from the 50th
is genuinely comparable across tiles in a way that |z| would not be.
"""

from brief.pipeline import Tile


def rank_anomalies(tiles: list[Tile], top: int = 5) -> list[Tile]:
    usable = [t for t in tiles if t.error is None and t.pctile is not None]
    return sorted(usable, key=lambda t: abs(t.pctile - 50.0), reverse=True)[:top]
```

Sorting is stable, so `c` at 2.0 (distance 48) precedes `b` at 97.0 (distance 47) as the first test asserts.

- [ ] **Step 4: Wire it into the payload**

In `src/brief/pipeline.py`, replace `build_payload` with:

```python
def build_payload(levels: dict[str, pd.Series]) -> dict:
    from brief.rank import rank_anomalies

    tiles = [_tile_for(metric, levels) for metric in REGISTRY.values()]
    setup = next((t for t in tiles if t.name == "divergence" and t.error is None), None)
    return {
        "date": str(date.today()),
        "tiles": tiles,
        "unusual": rank_anomalies(tiles),
        "setup": setup,
    }
```

The import is local to avoid a circular import: `rank` imports `Tile` from `pipeline`.

- [ ] **Step 5: Add the two sections to the template**

In `src/brief/render/template.html`, insert immediately after the closing `</header>` tag and before `<h2>Metrics</h2>`:

```html
  <h2>What's unusual today</h2>
  {% if payload.unusual %}
  <ol>
    {% for tile in payload.unusual %}
      <li>{{ tile.sentence }} <span class="pct">({{ "%.0f"|format(tile.pctile) }}th pct)</span></li>
    {% endfor %}
  </ol>
  {% else %}
  <p class="sentence">No metric is available today.</p>
  {% endif %}

  {% if payload.setup %}
  <h2>Setup</h2>
  <section class="tile">
    <p class="value">{{ "%+.0f"|format(payload.setup.value) }}</p>
    {{ strip(payload.setup.pctile) }}
    <p class="sentence">{{ payload.setup.sentence }}</p>
    <p class="asof">as of {{ payload.setup.as_of }}</p>
  </section>
  {% endif %}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest -v`
Expected: PASS, all tests

- [ ] **Step 7: Rebuild and read it as a brief**

```bash
.venv/bin/python -m brief.cli build && open dist/index.html
```

Expected: the page opens with five ranked sentences, then the setup block, then the tile grid. Read it top to bottom and time yourself — it should take under ninety seconds. If it does not, the sentences are too long.

- [ ] **Step 8: Commit**

```bash
git add src/brief/rank.py src/brief/pipeline.py src/brief/render/template.html tests/test_rank.py
git commit -m "feat: add anomaly ranker and final brief layout"
```

---

## Task 9: Staleness, resilience, and the golden test

A source outage must degrade the page, never blank it or lie about freshness.

**Files:**
- Modify: `src/brief/pipeline.py`, `src/brief/render/template.html`
- Create: `tests/test_golden.py`, `tests/fixtures/golden_payload.json`
- Test: `tests/test_golden.py`, `tests/test_render.py`

**Interfaces:**
- Consumes: everything prior.
- Produces: `pipeline.STALE_AFTER_DAYS: dict[str, int]`; `pipeline.load_levels` returns `(levels, source_status)` where `source_status: dict[str, str]`; `build_payload(levels, source_status=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render.py`:

```python
def test_a_tile_older_than_its_cadence_is_marked_stale():
    levels = synthetic_levels()  # ends in 2021, far past any cadence
    payload = build_payload(levels)
    assert payload["tiles"][0].stale is True
    assert "stale" in render(payload)


def test_source_failures_appear_in_the_header():
    payload = build_payload(synthetic_levels(), source_status={"cftc": "HTTP 503"})
    html = render(payload)
    assert "cftc" in html
    assert "503" in html
```

`tests/test_golden.py`:

```python
"""Pins the computed numbers so a refactor cannot silently change them."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from brief.metrics import cross_asset  # noqa: F401
from brief.pipeline import build_payload

GOLDEN = Path(__file__).parent / "fixtures" / "golden_payload.json"


def frozen_levels():
    idx = pd.bdate_range("2018-01-01", periods=1500)
    rng = np.random.default_rng(42)
    shock = rng.normal(size=1500)
    return {
        "equity": pd.Series(100 * np.exp(np.cumsum(shock * 0.01)), index=idx),
        "ust10": pd.Series(4.0 + np.cumsum(shock * 0.02), index=idx),
        "hy": pd.Series(4.0 + np.cumsum(rng.normal(size=1500) * 0.01), index=idx),
        "vix": pd.Series(18.0 + np.cumsum(rng.normal(size=1500) * 0.05), index=idx),
    }


def computed():
    payload = build_payload(frozen_levels())
    return {
        tile.name: None if tile.error else round(tile.value, 8)
        for tile in payload["tiles"]
    }


def test_computed_values_match_the_golden_file():
    expected = json.loads(GOLDEN.read_text())
    actual = computed()
    assert actual.keys() == expected.keys()
    for name, value in expected.items():
        if value is None:
            assert actual[name] is None
        else:
            assert actual[name] == pytest.approx(value, abs=1e-8)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_render.py tests/test_golden.py -v`
Expected: FAIL — `TypeError: build_payload() got an unexpected keyword argument 'source_status'`, and `FileNotFoundError` for the golden file.

- [ ] **Step 3: Implement staleness and status**

In `src/brief/pipeline.py`, add near the top:

```python
from datetime import timedelta

# How old a metric's newest observation may be before the tile is marked stale.
# CoT is weekly and already three days old when published, so it gets a wide gate.
STALE_AFTER_DAYS = {"daily": 5, "weekly": 12}


def _staleness_gate(metric) -> int:
    return STALE_AFTER_DAYS["weekly"] if metric.name.startswith(("pos_", "divergence")) else STALE_AFTER_DAYS["daily"]
```

In `_tile_for`, immediately before the final `return Tile(...)`, compute the flag and pass it:

```python
    last = series.index[-1].date()
    stale = (date.today() - last) > timedelta(days=_staleness_gate(metric))
```

and add `stale=stale,` to that `Tile(...)` call.

Then change the two signatures:

```python
def load_levels() -> tuple[dict[str, pd.Series], dict[str, str]]:
    """Fetch everything. A failing source degrades the page, never blanks it."""
    from brief.config import CONTRACTS
    from brief.sources.cftc import fetch as fetch_cot

    levels: dict[str, pd.Series] = {}
    status: dict[str, str] = {}
    for key, definition in SERIES.items():
        try:
            levels[key] = fetch(definition.fred_id)
        except Exception as exc:
            status[f"fred:{definition.fred_id}"] = str(exc)[:120]
    for key in CONTRACTS:
        try:
            levels[f"cot_{key}"] = fetch_cot(key)
        except Exception as exc:
            status[f"cftc:{key}"] = str(exc)[:120]
    return levels, status


def build_payload(levels: dict[str, pd.Series], source_status: dict[str, str] | None = None) -> dict:
    from brief.rank import rank_anomalies

    tiles = [_tile_for(metric, levels) for metric in REGISTRY.values()]
    setup = next((t for t in tiles if t.name == "divergence" and t.error is None), None)
    return {
        "date": str(date.today()),
        "tiles": tiles,
        "unusual": rank_anomalies(tiles),
        "setup": setup,
        "source_status": source_status or {},
    }
```

In `src/brief/cli.py`, update `main` to unpack the tuple:

```python
    levels, status = load_levels()
    payload = build_payload(levels, source_status=status)
```

and after the existing print, add:

```python
    for source, message in status.items():
        print(f"source failed: {source}: {message}", file=sys.stderr)
```

- [ ] **Step 4: Show source status in the header**

In `src/brief/render/template.html`, replace the `<span class="meta">{{ payload.date }}</span>` line with:

```html
    <span class="meta">
      {{ payload.date }}
      {% if payload.source_status %}
        · {% for source, message in payload.source_status.items() %}{{ source }} failed ({{ message }}){% if not loop.last %}, {% endif %}{% endfor %}
      {% else %}
        · sources ok
      {% endif %}
    </span>
```

- [ ] **Step 5: Generate the golden file**

```bash
.venv/bin/python -c "
import json, pathlib, sys
sys.path.insert(0, 'tests')
from test_golden import computed
pathlib.Path('tests/fixtures/golden_payload.json').write_text(json.dumps(computed(), indent=2))
print(pathlib.Path('tests/fixtures/golden_payload.json').read_text())
"
```

Read the printed values before accepting them. The `stock_bond` value must lie in [-1, 1] and `comovement` must be absent (its inputs are not in the frozen set, so that tile carries an error and serialises as `null`). If anything looks wrong, the bug is in the metric, not the golden file — never regenerate a golden file to make a failing test pass.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest -v`
Expected: PASS, all tests

- [ ] **Step 7: Commit**

```bash
git add src/brief/pipeline.py src/brief/cli.py src/brief/render/template.html tests/test_golden.py tests/test_render.py tests/fixtures/golden_payload.json
git commit -m "feat: degrade gracefully on source failure, mark stale tiles, pin numbers with a golden test"
```

---

## Task 10: Deploy and document

**Files:**
- Create: `.github/workflows/daily.yml`, `README.md`
- Test: manual — a green Action run and a gated live URL.

**Interfaces:**
- Consumes: `python -m brief.cli build` writing `dist/`.
- Produces: a deployed, access-gated site.

- [ ] **Step 1: Write the workflow**

`.github/workflows/daily.yml`:

```yaml
name: daily brief

on:
  schedule:
    - cron: "30 12 * * 1-5"   # 12:30 UTC weekdays, after the FRED morning update
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest -q
      - run: python -m brief.cli build
        env:
          FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
      - uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: pages deploy dist --project-name=cross-asset-brief
```

Tests run before the build, so a broken metric never deploys. If the build fails, Cloudflare keeps the previous deployment and GitHub emails the failure.

- [ ] **Step 2: Create the Cloudflare project and secrets**

1. Create a free Cloudflare account. Under **Workers & Pages**, create a Pages project named `cross-asset-brief` (choose "Direct Upload").
2. Create an API token with the **Cloudflare Pages: Edit** permission. Copy the account id from the dashboard sidebar.
3. In the GitHub repository, add three secrets under Settings → Secrets and variables → Actions: `FRED_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.

- [ ] **Step 3: Run the workflow manually and verify**

Push, then trigger the workflow from the Actions tab via "Run workflow".

Expected: a green run, and the site live at `https://cross-asset-brief.pages.dev`. Open it on a phone and confirm it collapses to one column and remains readable.

- [ ] **Step 4: Gate the site with Cloudflare Access**

In the Cloudflare dashboard under **Zero Trust → Access → Applications**, add a self-hosted application for `cross-asset-brief.pages.dev` with one policy: action **Allow**, rule **Emails**, value your own email address. Free for up to 50 users.

Expected: opening the URL in a private window now prompts for a one-time code rather than showing the brief.

- [ ] **Step 5: Write the README**

`README.md` — core only. No data, no roadmap sprawl, no badges.

```markdown
# Cross-asset daily brief

A once-daily macro brief that surfaces what is statistically unusual today
rather than what the levels are. Built from two public sources: FRED and the
CFTC Commitments of Traders.

## Why these metrics

Every tile has to earn its place by showing something a consumer finance app
cannot. A level or a price fails that test; a percentile, a positioning
extreme, or a cross-asset relationship passes it.

| Metric | Definition |
|---|---|
| Stock-bond regime | 60d correlation of Wilshire 5000 returns vs 10y yield changes, percentiled over the full common history |
| Credit vs vol divergence | 5y percentile of HY OAS minus 5y percentile of VIX |
| Cross-asset co-movement | Mean pairwise absolute 60d correlation across equity, 10y, dollar, HY, crude and VIX |
| Positioning | Net non-commercial position per contract, percentile over 3 years |
| Positioning-price divergence | 3y positioning percentile minus 3m price percentile |
| Anomaly ranker | Every metric ranked by distance from its 50th percentile |

## Why explainable over sophisticated

No metric in this system has a fitted parameter. Correlations, percentile
ranks and threshold rules only.

PCA was considered for cross-asset co-movement and rejected: rolling loadings
flip sign, the rotation needs hand-waving, and "percent variance explained
today" is undefined without a window. Mean pairwise absolute correlation
answers the same question in one sentence. Z-scores were rejected for
percentiles, which survive fat tails and explain themselves. A metric that
cannot state its meaning in one sentence cannot be registered — the registry
enforces it.

## Running it

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
export FRED_API_KEY=<key from fred.stlouisfed.org>
.venv/bin/pytest
.venv/bin/python -m brief.cli build   # writes dist/index.html
```

`scripts/smoke.py` checks every configured series and contract against the live
APIs. It is deliberately excluded from CI.
```

Add one screenshot of the rendered page and reference it under the title.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/daily.yml README.md
git commit -m "feat: add daily workflow, Cloudflare Pages deploy, and README"
```

---

## Self-Review Notes

**Spec coverage.** Every spec section maps to a task: sources → Tasks 2 and 6; the six metrics → Tasks 3, 5, 7, 8; UI/UX → Tasks 4 and 8; failure and staleness → Task 9; testing → distributed with a golden test in Task 9; deployment → Task 10.

**Two deviations from the spec, both deliberate and recorded here:**

1. The spec lists gold among the divergence contracts. FRED carries no verified free daily gold series, so gold appears in positioning percentiles but is excluded from divergence, which needs a price. Task 6 Step 3 records this.
2. The spec describes metric 5 generically; this plan computes it for E-mini S&P 500 only. Extending it per contract is a loop over `CONTRACTS` filtered on `price_series is not None` and is left for v2, when the contract set stabilises.

**Verification steps are load-bearing.** Task 2 Step 3 and Task 6 Step 1 exist because FRED series ids and CFTC field names cannot be confirmed from memory. Both steps state the command to run and the decision rule to apply. Do not skip them and do not guess the values.

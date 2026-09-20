"""Cross-source reconciliation.

Part of this board comes from Yahoo, which is unofficial. That is defensible
only if it is checked: where two providers carry the same thing, compare them
and put the answer on the page rather than quietly trusting one.

The comparison is made on the latest date the two sources share, never on each
source's own last observation. Publication lag is not disagreement — FRED's
crude ran three days behind Yahoo's during a week crude moved ten percent, and
comparing last-to-last would have reported a 10% divergence that was entirely
staleness.
"""

from dataclasses import dataclass

import pandas as pd

# key -> (label, (partner source, partner id), tolerance in percent)
CheckSpec = dict[str, tuple[str, tuple[str, str], float]]


@dataclass(frozen=True)
class CheckResult:
    key: str
    label: str
    ours: float | None
    theirs: float | None
    diff_pct: float | None
    as_of: str | None
    ok: bool
    note: str = ""


def run_checks(levels: dict[str, pd.Series], specs: CheckSpec, fetch) -> list[CheckResult]:
    """Compare each configured pair. A failure to check is itself a result."""
    results: list[CheckResult] = []

    for key, (label, (source, series_id), tolerance) in specs.items():
        ours = levels.get(key)
        if ours is None:
            continue

        try:
            theirs = fetch(source, series_id)
        except Exception as exc:
            results.append(
                CheckResult(key, label, None, None, None, None, False, str(exc)[:80])
            )
            continue

        shared = ours.dropna().index.intersection(theirs.dropna().index)
        if shared.empty:
            results.append(
                CheckResult(key, label, None, None, None, None, False, "no shared date")
            )
            continue

        when = shared.max()
        a, b = float(ours.loc[when]), float(theirs.loc[when])
        diff_pct = abs(a - b) / abs(b) * 100.0 if b else float("inf")
        results.append(
            CheckResult(
                key=key,
                label=label,
                ours=a,
                theirs=b,
                diff_pct=diff_pct,
                as_of=str(when.date()),
                ok=diff_pct <= tolerance,
                note="" if diff_pct <= tolerance else f"differ by {diff_pct:.2f}%",
            )
        )

    return results

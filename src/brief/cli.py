"""Build the static site. `python -m brief.cli build`"""

import sys
from pathlib import Path

from brief.metrics import cross_asset, positioning  # noqa: F401  (registers metrics)
from brief.pipeline import (
    build_payload,
    load_fed_path,
    load_levels,
    load_schedule,
    run_cross_checks,
)
from brief.render.page import render

DIST = Path("dist")


def main() -> int:
    levels, status = load_levels()
    calendar, schedule_failures = load_schedule()
    status.update(schedule_failures)
    fed_path, fed_summary = load_fed_path(levels)
    payload = build_payload(
        levels,
        source_status=status,
        checks=run_cross_checks(levels),
        calendar=calendar,
        fed_path=fed_path,
        fed_summary=fed_summary,
    )
    DIST.mkdir(exist_ok=True)
    (DIST / "index.html").write_text(render(payload), encoding="utf-8")
    broken = [t.name for t in payload["tiles"] if t.error]
    print(f"built dist/index.html — {len(payload['tiles'])} tiles, {len(broken)} unavailable")
    if broken:
        print(f"unavailable: {', '.join(broken)}", file=sys.stderr)
    for source, message in status.items():
        print(f"source failed: {source}: {message}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

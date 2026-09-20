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

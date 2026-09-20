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

"""Small text-formatting helpers shared by interpretations and the template."""


def ordinal(n: float) -> str:
    """1st, 2nd, 3rd, 4th ... 11th, 12th, 13th, 21st."""
    i = int(round(n))
    if 10 <= i % 100 <= 20:
        return f"{i}th"
    return f"{i}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(i % 10, 'th') }"

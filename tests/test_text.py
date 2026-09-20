from brief.text import ordinal


def test_ordinal_covers_the_standard_cases():
    cases = {
        1: "1st",
        2: "2nd",
        3: "3rd",
        4: "4th",
        11: "11th",
        12: "12th",
        13: "13th",
        21: "21st",
        72: "72nd",
        100: "100th",
    }
    for n, expected in cases.items():
        assert ordinal(n) == expected

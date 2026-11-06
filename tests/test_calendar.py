"""The scheduled-events feed."""

import json

from brief.calendar import Event, order, parse_auctions, parse_fed_calendar, parse_fred_releases

WINDOW = ("2026-11-06", "2026-11-13")


def test_only_the_releases_a_desk_watches_survive_the_filter():
    payload = {
        "release_dates": [
            {"date": "2026-11-06", "release_name": "Employment Situation"},
            {"date": "2026-11-06", "release_name": "Coinbase Cryptocurrencies"},
            {"date": "2026-11-06", "release_name": "Dow Jones Averages"},
            {"date": "2026-11-10", "release_name": "Consumer Price Index"},
        ]
    }
    labels = [e.label for e in parse_fred_releases(payload, *WINDOW)]
    assert labels == ["Employment Situation", "Consumer Price Index"]


def test_releases_outside_the_window_are_dropped():
    payload = {
        "release_dates": [
            {"date": "2026-10-01", "release_name": "Employment Situation"},
            {"date": "2026-12-01", "release_name": "Employment Situation"},
        ]
    }
    assert parse_fred_releases(payload, *WINDOW) == []


def test_fed_events_combine_month_and_day_into_a_date():
    raw = json.dumps(
        {"events": [{"month": "2026-11", "days": "13", "time": "7:00 p.m.",
                     "title": "Speech - Vice Chair Philip N. Jefferson"}]}
    ).encode()
    event = parse_fed_calendar(raw, *WINDOW)[0]
    assert event.date == "2026-11-13"
    assert event.time == "7:00 p.m."
    assert event.kind == "fed"


def test_a_two_day_fomc_meeting_lands_on_its_first_day():
    raw = json.dumps(
        {"events": [{"month": "2026-11", "days": "10-11", "time": "2:00 p.m.",
                     "title": "FOMC Meeting"}]}
    ).encode()
    assert parse_fed_calendar(raw, *WINDOW)[0].date == "2026-11-10"


def test_the_fed_feed_is_read_through_its_byte_order_mark():
    """federalreserve.gov serves calendar.json with a UTF-8 BOM; decoding it
    as plain utf-8 raises before anything else can go wrong."""
    raw = b"\xef\xbb\xbf" + json.dumps(
        {"events": [{"month": "2026-11", "days": "6", "time": "", "title": "FOMC Press Release"}]}
    ).encode()
    assert parse_fed_calendar(raw, *WINDOW)[0].label == "FOMC Press Release"


def test_an_event_with_an_unparseable_day_is_skipped_not_fatal():
    raw = json.dumps({"events": [{"month": "2026-11", "days": "TBA", "title": "x"}, {}]}).encode()
    assert parse_fed_calendar(raw, *WINDOW) == []


def test_an_auction_uses_the_close_date_because_auction_date_is_null_until_after():
    rows = [{
        "competitiveAuctionCloseDate": "2026-11-09T00:00:00",
        "auctionDate": None,
        "securityType": "Note",
        "securityTerm": "3-Year",
        "offeringAmount": "58000000000",
    }]
    event = parse_auctions(rows, *WINDOW)[0]
    assert event.date == "2026-11-09"
    assert event.label == "3-Year Note $58bn"
    assert event.kind == "auction"


def test_an_auction_with_no_size_still_lists():
    rows = [{"competitiveAuctionCloseDate": "2026-11-09T00:00:00",
             "securityType": "Bill", "securityTerm": "6-Week", "offeringAmount": None}]
    assert parse_auctions(rows, *WINDOW)[0].label == "6-Week Bill"


def test_ordering_is_by_date_then_fed_then_data_then_auctions():
    events = [
        Event("2026-11-09", "", "auction", "3-Year Note"),
        Event("2026-11-06", "", "data", "Employment Situation"),
        Event("2026-11-06", "2:00 p.m.", "fed", "FOMC Press Release"),
        Event("2026-11-06", "", "auction", "6-Week Bill"),
    ]
    assert [e.label for e in order(events)] == [
        "FOMC Press Release", "Employment Situation", "6-Week Bill", "3-Year Note",
    ]


def test_a_release_listed_on_consecutive_days_collapses_to_its_first():
    """FRED emits a date per day for some releases, so "FOMC Press Release"
    arrives three days running. Within a one-week window a release happens
    once; listing it three times buries everything else."""
    events = [
        Event("2026-11-06", "", "data", "FOMC Press Release"),
        Event("2026-11-07", "", "data", "FOMC Press Release"),
        Event("2026-11-08", "", "data", "FOMC Press Release"),
        Event("2026-11-07", "", "data", "Employment Situation"),
    ]
    out = order(events)
    assert [(e.date, e.label) for e in out] == [
        ("2026-11-06", "FOMC Press Release"),
        ("2026-11-07", "Employment Situation"),
    ]


def test_the_same_label_from_different_feeds_is_kept_once():
    events = [
        Event("2026-11-06", "3:00 p.m.", "fed", "G.19 - Consumer Credit"),
        Event("2026-11-06", "", "data", "G.19 - Consumer Credit"),
    ]
    assert len(order(events)) == 1


def test_variants_of_one_release_collapse_to_the_headline_name():
    """FRED lists "Consumer Price Index", "...Excluding Energy Commodities"
    and "Research Consumer Price Index" as three releases on the same day.
    A desk watches one CPI. The shortest matching name is the headline."""
    payload = {
        "release_dates": [
            {"date": "2026-11-10", "release_name": "Consumer Price Index Excluding Energy Commodities"},
            {"date": "2026-11-10", "release_name": "Research Consumer Price Index"},
            {"date": "2026-11-10", "release_name": "Consumer Price Index"},
        ]
    }
    events = parse_fred_releases(payload, *WINDOW)
    assert [e.label for e in events] == ["Consumer Price Index"]


def test_two_genuinely_different_releases_both_survive():
    payload = {
        "release_dates": [
            {"date": "2026-11-10", "release_name": "Consumer Price Index"},
            {"date": "2026-11-13", "release_name": "Producer Price Index"},
        ]
    }
    assert len(parse_fred_releases(payload, *WINDOW)) == 2

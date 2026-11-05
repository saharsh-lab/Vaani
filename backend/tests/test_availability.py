"""Slot arithmetic, matching and parsing. No database needed."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.phones import InvalidPhone, mask_phone, normalize_phone
from app.services.availability import (
    WINDOWS,
    Interval,
    StaffDay,
    TimePreference,
    choose_slots,
    day_intervals,
    free_starts,
    parse_preference,
    slot_label,
    slot_starts,
    subtract,
)
from app.services.knowledge import to_or_query
from app.services.scheduling import best_match

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 11, 3)
MIN15 = timedelta(minutes=15)
MIN30 = timedelta(minutes=30)
WORK = day_intervals(DAY, [(time(10), time(13, 30)), (time(17), time(21))], IST)


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 3, hour, minute, tzinfo=IST)


def hhmm(starts: list[datetime]) -> list[str]:
    return [s.strftime("%H:%M") for s in starts]


def test_subtract_splits_around_busy_time():
    free = subtract([Interval(at(10), at(13))], [Interval(at(11), at(11, 30))])
    assert free == [Interval(at(10), at(11)), Interval(at(11, 30), at(13))]


def test_subtract_handles_busy_covering_everything():
    assert subtract([Interval(at(10), at(11))], [Interval(at(9), at(12))]) == []


def test_slots_must_finish_before_closing():
    starts = slot_starts([Interval(at(12), at(13, 30))], timedelta(minutes=45), MIN15, at(0))
    assert hhmm(starts) == ["12:00", "12:15", "12:30", "12:45"]


def test_not_before_rounds_up_to_the_quarter_hour():
    assert slot_starts(WORK, MIN30, MIN15, at(10, 7))[0] == at(10, 15)


def test_not_before_in_utc_still_aligns_to_local_clock():
    first = slot_starts(WORK, MIN30, MIN15, at(10, 7).astimezone(UTC))[0]
    assert first == at(10, 15)
    assert first.tzinfo == IST


def test_free_starts_uses_first_staff_and_falls_back_to_others():
    busy_a = StaffDay(uuid.uuid4(), "A", WORK, [Interval(at(10), at(11))])
    free_b = StaffDay(uuid.uuid4(), "B", WORK, [])
    starts = free_starts([busy_a, free_b], MIN30, MIN15, at(0))
    assert starts[at(10)].name == "B"
    assert starts[at(11)].name == "A"


def test_evening_window_spreads_choices():
    starts = slot_starts(WORK, MIN15, MIN15, at(0))
    assert hhmm(choose_slots(starts, parse_preference("evening"), 3, MIN30)) == [
        "17:00",
        "17:30",
        "18:00",
    ]


def test_specific_time_returns_nearest_slots():
    starts = [at(17), at(17, 30), at(18, 30), at(20)]
    assert hhmm(choose_slots(starts, parse_preference("6:15 pm"), 2, MIN30)) == ["17:30", "18:30"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, TimePreference()),
        ("any", TimePreference()),
        ("Evening", TimePreference(window=WINDOWS["evening"])),
        ("18:15", TimePreference(target=time(18, 15))),
        ("6pm", TimePreference(target=time(18))),
        ("6.30 pm", TimePreference(target=time(18, 30))),
        ("12 am", TimePreference(target=time(0))),
        ("sayantram", TimePreference(window=WINDOWS["evening"])),
        ("సాయంత్రం", TimePreference(window=WINDOWS["evening"])),
        ("Shaam", TimePreference(window=WINDOWS["evening"])),
        ("सुबह", TimePreference(window=WINDOWS["morning"])),
        ("podduna", TimePreference(window=WINDOWS["morning"])),
    ],
)
def test_parse_preference(raw, expected):
    assert parse_preference(raw) == expected


@pytest.mark.parametrize("raw", ["whenever", "25:00", "6:75"])
def test_parse_preference_rejects_nonsense(raw):
    with pytest.raises(ValueError):
        parse_preference(raw)


def test_slot_label_is_speakable():
    assert slot_label(at(18, 15)) == "Tue 3 Nov, 6:15 PM"
    assert slot_label(at(0, 5)) == "Tue 3 Nov, 12:05 AM"


SERVICES = ["General consultation", "RCT consultation", "Teeth cleaning"]


@pytest.mark.parametrize(
    ("wanted", "expected"),
    [
        ("rct consultation", "RCT consultation"),
        ("cleaning", "Teeth cleaning"),
        ("consultation", None),  # ambiguous: don't guess
        ("haircut", None),
    ],
)
def test_service_matching(wanted, expected):
    assert best_match(wanted, SERVICES, str) == expected


def test_staff_matching_ignores_titles():
    assert best_match("Lakshmi", ["Dr. Arjun Rao", "Dr. Lakshmi Reddy"], str) == "Dr. Lakshmi Reddy"


@pytest.mark.parametrize(
    "raw", ["9876543210", "98765 43210", "+91-98765-43210", "09876543210", "919876543210"]
)
def test_indian_numbers_normalise(raw):
    assert normalize_phone(raw) == "+919876543210"


def test_international_number_kept():
    assert normalize_phone("+1 415 555 0100") == "+14155550100"


@pytest.mark.parametrize("raw", ["12345", "", None, "call me"])
def test_invalid_numbers_rejected(raw):
    with pytest.raises(InvalidPhone):
        normalize_phone(raw)


def test_mask_phone():
    assert mask_phone("+919876543210") == "+91******3210"


def test_keyword_query_drops_stopwords_and_keeps_telugu_words_whole():
    assert to_or_query("Is there parking near the clinic?") == "parking | near | clinic"
    assert to_or_query("పార్కింగ్ ఉందా?") == "పార్కింగ్ | ఉందా"
    assert to_or_query("what is the?") is None

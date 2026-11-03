"""Slot arithmetic. Pure functions with no database access, so they're cheap to test.

All datetimes here are timezone-aware and in the business's local timezone.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

WINDOWS: dict[str, tuple[time, time]] = {
    "morning": (time(6), time(12)),
    "afternoon": (time(12), time(17)),
    "evening": (time(17), time(23, 59)),
    "night": (time(17), time(23, 59)),
}


@dataclass(frozen=True, order=True)
class Interval:
    start: datetime
    end: datetime

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, start: datetime, end: datetime) -> bool:
        return self.start <= start and end <= self.end


@dataclass
class StaffDay:
    """One staff member's working intervals and busy intervals for one day."""

    staff_id: uuid.UUID
    name: str
    work: list[Interval] = field(default_factory=list)
    busy: list[Interval] = field(default_factory=list)

    def free(self) -> list[Interval]:
        return subtract(self.work, self.busy)


@dataclass(frozen=True)
class TimePreference:
    window: tuple[time, time] | None = None
    target: time | None = None


def day_intervals(day: date, hours: list[tuple[time, time]], tz: ZoneInfo) -> list[Interval]:
    return sorted(
        Interval(datetime.combine(day, open_, tz), datetime.combine(day, close, tz))
        for open_, close in hours
    )


def subtract(free: list[Interval], busy: list[Interval]) -> list[Interval]:
    """Remove every busy interval from the free intervals."""
    result: list[Interval] = []
    for interval in free:
        pieces = [interval]
        for b in busy:
            remaining = []
            for p in pieces:
                if not p.overlaps(b):
                    remaining.append(p)
                    continue
                if p.start < b.start:
                    remaining.append(Interval(p.start, b.start))
                if b.end < p.end:
                    remaining.append(Interval(b.end, p.end))
            pieces = remaining
        result.extend(pieces)
    return sorted(result)


def ceil_to_step(dt: datetime, step: timedelta) -> datetime:
    """Round up to the next clock multiple of step (10:07 -> 10:15 for 15 min)."""
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    steps = -(-(dt - midnight) // step)
    return midnight + steps * step


def slot_starts(
    free: list[Interval], duration: timedelta, step: timedelta, not_before: datetime
) -> list[datetime]:
    starts = []
    for interval in free:
        t = ceil_to_step(max(interval.start, not_before.astimezone(interval.start.tzinfo)), step)
        while t + duration <= interval.end:
            starts.append(t)
            t += step
    return starts


def free_starts(
    staff_days: list[StaffDay], duration: timedelta, step: timedelta, not_before: datetime
) -> dict[datetime, StaffDay]:
    """Every bookable start time, mapped to the first listed staff member free then."""
    found: dict[datetime, StaffDay] = {}
    for sd in staff_days:
        for start in slot_starts(sd.free(), duration, step, not_before):
            found.setdefault(start, sd)
    return dict(sorted(found.items()))


def staff_free_for(staff_days: list[StaffDay], start: datetime, end: datetime) -> StaffDay | None:
    for sd in staff_days:
        if any(interval.contains(start, end) for interval in sd.free()):
            return sd
    return None


def parse_preference(raw: str | None) -> TimePreference:
    """Accepts morning / afternoon / evening / any, or a time like 18:15, 6pm, 6:15 pm."""
    text = (raw or "").strip().lower()
    if text in ("", "any", "anytime", "any time"):
        return TimePreference()
    if text in WINDOWS:
        return TimePreference(window=WINDOWS[text])
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?", text)
    if m:
        hour, minute, ampm = int(m[1]), int(m[2] or 0), m[3]
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        if hour < 24 and minute < 60:
            return TimePreference(target=time(hour, minute))
    raise ValueError(f"Unrecognised preferred_time {raw!r}")


def pick_spread(starts: list[datetime], count: int, min_gap: timedelta) -> list[datetime]:
    """Earliest slots, at least min_gap apart, so the caller gets a real choice."""
    picked: list[datetime] = []
    for s in starts:
        if not picked or s - picked[-1] >= min_gap:
            picked.append(s)
            if len(picked) == count:
                break
    return picked


def choose_slots(
    starts: list[datetime], pref: TimePreference, count: int, min_gap: timedelta
) -> list[datetime]:
    if pref.target is not None:
        target = pref.target.hour * 60 + pref.target.minute
        ranked = sorted(starts, key=lambda s: (abs(s.hour * 60 + s.minute - target), s))
        return sorted(ranked[:count])
    if pref.window is not None:
        lo, hi = pref.window
        starts = [s for s in starts if lo <= s.time() < hi]
    return pick_spread(starts, count, min_gap)


def slot_label(dt: datetime) -> str:
    """Tue 3 Nov, 6:15 PM"""
    hour = dt.hour % 12 or 12
    return f"{dt:%a} {dt.day} {dt:%b}, {hour}:{dt:%M} {'AM' if dt.hour < 12 else 'PM'}"


def day_label(day: date) -> str:
    return f"{day:%A} {day.day} {day:%B}"

"""Loads schedules from the database and answers check_availability."""

import re
import uuid
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.config import get_settings
from app.errors import InvalidRequest, NotFound
from app.models import BlockedSlot, Booking, Business, Service, Staff, StaffService, WorkingHours
from app.schemas import AvailabilityOut, CheckAvailabilityIn, DaySlotsOut, Slot
from app.services.availability import (
    Interval,
    StaffDay,
    TimePreference,
    choose_slots,
    day_intervals,
    day_label,
    free_starts,
    parse_preference,
    slot_label,
)

_IGNORED_WORDS = {"dr", "doctor", "the", "a", "an", "for", "appointment", "service"}


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^\w]+", text.lower()) if w and w not in _IGNORED_WORDS}


def best_match[T](wanted: str, candidates: list[T], key: Callable[[T], str]) -> T | None:
    """Exact (case-insensitive) match, else the single best word-overlap match."""
    target = wanted.strip().lower()
    for c in candidates:
        if key(c).lower() == target:
            return c
    wanted_words = _words(wanted)
    scored = []
    for c in candidates:
        words = _words(key(c))
        if wanted_words and words:
            overlap = len(wanted_words & words) / min(len(wanted_words), len(words))
            if overlap >= 0.5:
                scored.append((overlap, c))
    scored.sort(key=lambda pair: -pair[0])
    if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1]
    return None


async def resolve_service(session: AsyncSession, name: str) -> Service:
    services = (
        await session.scalars(select(Service).where(Service.active).order_by(Service.name))
    ).all()
    match = best_match(name, list(services), lambda s: s.name)
    if match is None:
        raise InvalidRequest(
            f"No service called {name!r}. Use one of the exact names listed.",
            services=[s.name for s in services],
        )
    return match


async def resolve_staff(session: AsyncSession, name: str) -> Staff:
    staff = (await session.scalars(select(Staff).where(Staff.active).order_by(Staff.name))).all()
    match = best_match(name, list(staff), lambda s: s.name)
    if match is None:
        raise NotFound(f"No staff member called {name!r}.", staff=[s.name for s in staff])
    return match


async def staff_for_service(session: AsyncSession, service_id: uuid.UUID) -> list[Staff]:
    rows = await session.scalars(
        select(Staff)
        .join(StaffService, StaffService.staff_id == Staff.id)
        .where(StaffService.service_id == service_id, Staff.active)
        .order_by(Staff.name)
    )
    return list(rows.all())


async def load_staff_days(
    session: AsyncSession,
    *,
    tz: ZoneInfo,
    service_id: uuid.UUID,
    day: date,
    staff_id: uuid.UUID | None = None,
    ignore_booking_id: uuid.UUID | None = None,
    prefer_staff_id: uuid.UUID | None = None,
) -> list[StaffDay]:
    """Working and busy time on `day` for each staff member who can do the service."""
    staff = [
        s for s in await staff_for_service(session, service_id) if not staff_id or s.id == staff_id
    ]
    if not staff:
        return []
    if prefer_staff_id:
        staff.sort(key=lambda s: s.id != prefer_staff_id)
    ids = [s.id for s in staff]

    day_start = datetime.combine(day, time(0), tz)
    day_end = day_start + timedelta(days=1)

    hours = (
        await session.scalars(
            select(WorkingHours).where(
                or_(WorkingHours.staff_id.is_(None), WorkingHours.staff_id.in_(ids))
            )
        )
    ).all()
    blocks = (
        await session.scalars(
            select(BlockedSlot).where(
                BlockedSlot.start_at < day_end,
                BlockedSlot.end_at > day_start,
                or_(BlockedSlot.staff_id.is_(None), BlockedSlot.staff_id.in_(ids)),
            )
        )
    ).all()
    booking_query = select(Booking.staff_id, Booking.start_at, Booking.end_at).where(
        Booking.status == "confirmed",
        Booking.staff_id.in_(ids),
        Booking.start_at < day_end,
        Booking.end_at > day_start,
    )
    if ignore_booking_id:
        booking_query = booking_query.where(Booking.id != ignore_booking_id)
    bookings = (await session.execute(booking_query)).all()

    weekday = day.weekday()
    has_own_hours = {h.staff_id for h in hours if h.staff_id is not None}
    default_hours = [
        (h.open_time, h.close_time) for h in hours if h.staff_id is None and h.weekday == weekday
    ]

    def local(start: datetime, end: datetime) -> Interval:
        return Interval(start.astimezone(tz), end.astimezone(tz))

    result = []
    for s in staff:
        if s.id in has_own_hours:
            own = [
                (h.open_time, h.close_time)
                for h in hours
                if h.staff_id == s.id and h.weekday == weekday
            ]
        else:
            own = default_hours
        busy = [local(b.start_at, b.end_at) for b in blocks if b.staff_id in (None, s.id)]
        busy += [local(b.start_at, b.end_at) for b in bookings if b.staff_id == s.id]
        result.append(StaffDay(s.id, s.name, day_intervals(day, own, tz), sorted(busy)))
    return result


def earliest_bookable(tz: ZoneInfo) -> datetime:
    return clock.now().astimezone(tz) + timedelta(minutes=get_settings().booking_lead_min)


async def find_slots(
    session: AsyncSession,
    *,
    tz: ZoneInfo,
    service: Service,
    start_day: date,
    pref: TimePreference,
    staff_id: uuid.UUID | None = None,
    count: int = 3,
) -> tuple[date | None, list[Slot], bool]:
    """Search forward from start_day for the first day with free slots.

    Returns (day, slots, matched_preference). If the day has slots but none in the
    preferred window, it returns other times that day with matched_preference=False.
    """
    settings = get_settings()
    duration = timedelta(minutes=service.duration_min)
    step = timedelta(minutes=settings.slot_step_min)
    gap = max(duration, timedelta(minutes=30))
    not_before = earliest_bookable(tz)

    for offset in range(settings.availability_search_days):
        day = start_day + timedelta(days=offset)
        staff_days = await load_staff_days(
            session, tz=tz, service_id=service.id, day=day, staff_id=staff_id
        )
        starts = free_starts(staff_days, duration, step, not_before)
        if not starts:
            continue
        chosen = choose_slots(list(starts), pref, count, gap)
        matched = bool(chosen)
        if not chosen:
            chosen = choose_slots(list(starts), TimePreference(), count, gap)
        slots = [Slot(start_at=s, label=slot_label(s), staff=starts[s].name) for s in chosen]
        return day, slots, matched
    return None, [], False


async def day_slots(
    session: AsyncSession, business: Business, service_name: str, day: date
) -> DaySlotsOut:
    """Every free start time on one day, for the booking page (the agent offers
    three; a form can show them all)."""
    settings = get_settings()
    tz = ZoneInfo(business.timezone)
    service = await resolve_service(session, service_name)
    today = clock.now().astimezone(tz).date()
    if not today <= day < today + timedelta(days=settings.public_book_days_ahead):
        raise InvalidRequest(f"Choose a day in the next {settings.public_book_days_ahead} days.")
    staff_days = await load_staff_days(session, tz=tz, service_id=service.id, day=day)
    starts = free_starts(
        staff_days,
        timedelta(minutes=service.duration_min),
        timedelta(minutes=settings.slot_step_min),
        earliest_bookable(tz),
    )
    slots = [Slot(start_at=s, label=slot_label(s), staff=starts[s].name) for s in sorted(starts)]
    next_free = None
    if not slots:
        next_free, _, _ = await find_slots(
            session,
            tz=tz,
            service=service,
            start_day=day + timedelta(days=1),
            pref=TimePreference(),
            count=1,
        )
    return DaySlotsOut(
        service=service.name,
        duration_min=service.duration_min,
        price_inr=float(service.price_inr) if service.price_inr is not None else None,
        date=day,
        slots=slots,
        next_free_date=next_free,
    )


async def check_availability(
    session: AsyncSession, business: Business, body: CheckAvailabilityIn
) -> AvailabilityOut:
    tz = ZoneInfo(business.timezone)
    service = await resolve_service(session, body.service)

    staff_id = None
    if body.staff:
        staff = await resolve_staff(session, body.staff)
        able = await staff_for_service(session, service.id)
        if staff.id not in {s.id for s in able}:
            raise InvalidRequest(
                f"{staff.name} doesn't do {service.name}.", staff=[s.name for s in able]
            )
        staff_id = staff.id

    try:
        pref = parse_preference(body.preferred_time)
    except ValueError as exc:
        raise InvalidRequest(f"{exc}. Use morning, afternoon, evening, any, or HH:MM.") from exc

    today = clock.now().astimezone(tz).date()
    if body.date < today:
        raise InvalidRequest(f"{body.date} is in the past; today is {today}.")

    day, slots, matched = await find_slots(
        session, tz=tz, service=service, start_day=body.date, pref=pref, staff_id=staff_id
    )

    note = None
    days = get_settings().availability_search_days
    if day is None:
        note = f"No free slots in the next {days} days. Offer a callback from the team."
    elif day != body.date:
        note = f"Nothing free on {day_label(body.date)}. The next free day is {day_label(day)}."
    if day is not None and not matched:
        extra = f"None of these are in the requested time ({body.preferred_time})."
        note = f"{note} {extra}" if note else extra

    return AvailabilityOut(
        service=service.name,
        duration_min=service.duration_min,
        price_inr=float(service.price_inr) if service.price_inr is not None else None,
        date=day or body.date,
        slots=slots,
        note=note,
    )

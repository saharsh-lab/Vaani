"""create_booking, find_booking and reschedule_or_cancel.

Each call runs inside the request's tenant transaction. The availability check
below gives friendly errors; the bookings_no_overlap constraint is what actually
guarantees no double booking when two callers race for the same slot.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.errors import InvalidRequest, NotFound, SlotUnavailable
from app.models import Booking, Business, Customer, Service, Staff
from app.phones import InvalidPhone, mask_phone, normalize_phone
from app.schemas import (
    BookingOut,
    BookingsOut,
    CreateBookingIn,
    FindBookingIn,
    RescheduleOrCancelIn,
)
from app.services.availability import TimePreference, slot_label, staff_free_for
from app.services.scheduling import (
    earliest_bookable,
    find_slots,
    load_staff_days,
    resolve_service,
    resolve_staff,
)

log = logging.getLogger(__name__)

EXCLUSION_VIOLATION = "23P01"


def _phone(raw: str) -> str:
    try:
        return normalize_phone(raw)
    except InvalidPhone as exc:
        raise InvalidRequest(
            f"{raw!r} doesn't look like a phone number. Ask for the 10-digit mobile number."
        ) from exc


def _local(dt: datetime, tz: ZoneInfo) -> datetime:
    """Naive datetimes from the LLM are the business's local time."""
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)


def _view(booking: Booking, service: str, staff: str, customer: str | None, tz: ZoneInfo):
    start = booking.start_at.astimezone(tz)
    return BookingOut(
        booking_id=booking.id,
        service=service,
        staff=staff,
        start_at=start,
        label=slot_label(start),
        status=booking.status,
        customer_name=customer,
    )


async def _alternatives(
    session: AsyncSession, tz: ZoneInfo, service: Service, near: datetime
) -> list[dict]:
    _, slots, _ = await find_slots(
        session,
        tz=tz,
        service=service,
        start_day=max(near.date(), earliest_bookable(tz).date()),
        pref=TimePreference(target=near.time()),
    )
    return [s.model_dump(mode="json") for s in slots]


async def _check_bookable(
    session: AsyncSession,
    tz: ZoneInfo,
    service: Service,
    start: datetime,
    *,
    staff_id: uuid.UUID | None = None,
    ignore_booking_id: uuid.UUID | None = None,
    prefer_staff_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Return the staff member who will take the slot, or raise with alternatives."""
    if start < earliest_bookable(tz):
        raise InvalidRequest(
            "That time has passed or is too soon to book.",
            alternatives=await _alternatives(session, tz, service, start),
        )
    end = start + timedelta(minutes=service.duration_min)
    staff_days = await load_staff_days(
        session,
        tz=tz,
        service_id=service.id,
        day=start.date(),
        staff_id=staff_id,
        ignore_booking_id=ignore_booking_id,
        prefer_staff_id=prefer_staff_id,
    )
    chosen = staff_free_for(staff_days, start, end)
    if chosen is None:
        raise SlotUnavailable(
            f"{slot_label(start)} is not available for {service.name}.",
            alternatives=await _alternatives(session, tz, service, start),
        )
    return chosen.staff_id


async def _write_or_conflict(
    session: AsyncSession,
    tz: ZoneInfo,
    service: Service,
    start: datetime,
    apply: Callable[[], None],
) -> None:
    """Apply and flush a change inside a savepoint, so losing a race to another
    booking becomes a 409 instead of aborting the whole transaction.

    The change must be made inside the savepoint: begin_nested() flushes pending
    changes before the SAVEPOINT exists, where a conflict can't be rolled back.
    """
    try:
        async with session.begin_nested():
            apply()
            await session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) != EXCLUSION_VIOLATION:
            raise
        raise SlotUnavailable(
            f"{slot_label(start)} was just taken by someone else.",
            alternatives=await _alternatives(session, tz, service, start),
        ) from exc


async def create_booking(
    session: AsyncSession, business: Business, body: CreateBookingIn
) -> BookingOut:
    tz = ZoneInfo(business.timezone)
    service = await resolve_service(session, body.service)
    staff_id = (await resolve_staff(session, body.staff)).id if body.staff else None
    phone = _phone(body.phone)
    start = _local(body.start_at, tz)

    chosen_staff = await _check_bookable(session, tz, service, start, staff_id=staff_id)

    insert_customer = insert(Customer).values(
        id=uuid.uuid4(), business_id=business.id, phone=phone, name=body.customer_name.strip()
    )
    customer_id = await session.scalar(
        insert_customer.on_conflict_do_update(
            index_elements=[Customer.business_id, Customer.phone],
            # Keep the name we already have; a caller may book for a family member.
            set_={"name": func.coalesce(Customer.name, insert_customer.excluded.name)},
        ).returning(Customer.id)
    )

    booking = Booking(
        business_id=business.id,
        customer_id=customer_id,
        service_id=service.id,
        staff_id=chosen_staff,
        conversation_id=body.conversation_id,
        start_at=start,
        end_at=start + timedelta(minutes=service.duration_min),
        source=body.source,
        customer_name=body.customer_name.strip(),
    )
    await _write_or_conflict(session, tz, service, start, lambda: session.add(booking))

    staff_name = await session.scalar(select(Staff.name).where(Staff.id == chosen_staff))
    log.info("booking %s created for %s at %s", booking.id, mask_phone(phone), start.isoformat())
    return _view(booking, service.name, staff_name, body.customer_name.strip(), tz)


async def find_bookings(
    session: AsyncSession, business: Business, body: FindBookingIn
) -> BookingsOut:
    tz = ZoneInfo(business.timezone)
    phone = _phone(body.phone)
    rows = await session.execute(
        select(
            Booking, Service.name, Staff.name, func.coalesce(Booking.customer_name, Customer.name)
        )
        .join(Customer, Customer.id == Booking.customer_id)
        .join(Service, Service.id == Booking.service_id)
        .join(Staff, Staff.id == Booking.staff_id)
        .where(
            Customer.phone == phone,
            Booking.status == "confirmed",
            Booking.start_at >= clock.now(),
        )
        .order_by(Booking.start_at)
        .limit(5)
    )
    return BookingsOut(bookings=[_view(b, svc, staff, cust, tz) for b, svc, staff, cust in rows])


async def reschedule_or_cancel(
    session: AsyncSession, business: Business, body: RescheduleOrCancelIn
) -> BookingOut:
    tz = ZoneInfo(business.timezone)
    row = (
        await session.execute(
            select(Booking, Customer.phone, func.coalesce(Booking.customer_name, Customer.name))
            .join(Customer, Customer.id == Booking.customer_id)
            .where(Booking.id == body.booking_id)
            .with_for_update(of=Booking)
        )
    ).one_or_none()
    # A verified caller may only change their own bookings; don't reveal others exist.
    if row is None or (body.caller_phone and row.phone != _phone(body.caller_phone)):
        raise NotFound("No booking with that id for this caller. Use find_booking first.")
    booking, _, customer_name = row

    if booking.status != "confirmed":
        raise InvalidRequest(f"This booking is already {booking.status}.")
    if booking.start_at < clock.now():
        raise InvalidRequest("This booking is in the past and can't be changed.")

    service = await session.get(Service, booking.service_id)

    if body.action == "cancel":
        booking.status = "cancelled"
        booking.updated_at = clock.now()
        await session.flush()
    else:
        if body.new_start_at is None:
            raise InvalidRequest("new_start_at is required to reschedule.")
        start = _local(body.new_start_at, tz)
        new_staff = await _check_bookable(
            session,
            tz,
            service,
            start,
            ignore_booking_id=booking.id,
            prefer_staff_id=booking.staff_id,
        )

        def move() -> None:
            booking.staff_id = new_staff
            booking.start_at = start
            booking.end_at = start + timedelta(minutes=service.duration_min)
            booking.updated_at = clock.now()

        await _write_or_conflict(session, tz, service, start, move)

    staff_name = await session.scalar(select(Staff.name).where(Staff.id == booking.staff_id))
    log.info("booking %s %s", booking.id, booking.status if body.action == "cancel" else "moved")
    return _view(booking, service.name, staff_name, customer_name, tz)

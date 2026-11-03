"""Queries behind the owner and staff dashboards.

Every function runs in the signed-in user's tenant session, so row-level security
limits it to their business; nothing here filters on business_id by hand.
"""

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.auth import hash_password
from app.models import (
    BlockedSlot,
    Booking,
    Business,
    Conversation,
    Customer,
    KbChunk,
    KbDocument,
    Message,
    Service,
    Staff,
    StaffService,
    User,
    WorkingHours,
)
from app.schemas_dashboard import (
    BlockedIn,
    BlockedRow,
    BookingRow,
    BusinessOut,
    BusinessPatch,
    ConversationDetail,
    ConversationRow,
    ConversationsOut,
    FaqIn,
    FaqRow,
    HandoffRow,
    HoursRow,
    MemberIn,
    MemberPatch,
    MessageRow,
    Overview,
    ServiceIn,
    ServicePatch,
    ServiceRow,
    StaffIn,
    StaffPatch,
    StaffRow,
    UserOut,
)


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def business_out(b: Business) -> BusinessOut:
    return BusinessOut(
        id=b.id,
        slug=b.slug,
        name=b.name,
        type=b.type,
        timezone=b.timezone,
        languages=b.languages,
        greeting=b.greeting,
        address=b.address,
        phone=b.phone,
        whatsapp_connected=bool(b.whatsapp_phone_number_id),
    )


def user_out(u: User) -> UserOut:
    return UserOut(id=u.id, name=u.name, email=u.email, role=u.role, active=u.active)


# Bookings ---------------------------------------------------------------------------

BOOKING_COLUMNS = (
    Booking,
    Service.name,
    Staff.name,
    func.coalesce(Booking.customer_name, Customer.name),
    Customer.phone,
)


def _booking_query():
    return (
        select(*BOOKING_COLUMNS)
        .join(Service, Service.id == Booking.service_id)
        .join(Staff, Staff.id == Booking.staff_id)
        .join(Customer, Customer.id == Booking.customer_id)
    )


def _booking_row(row, tz: ZoneInfo) -> BookingRow:
    b, service, staff, customer_name, phone = row
    return BookingRow(
        id=b.id,
        start_at=b.start_at.astimezone(tz),
        end_at=b.end_at.astimezone(tz),
        status=b.status,
        source=b.source,
        service=service,
        staff=staff,
        staff_id=b.staff_id,
        customer_name=customer_name,
        customer_phone=phone,
        conversation_id=b.conversation_id,
    )


async def bookings(
    db: AsyncSession, tz: ZoneInfo, *, start: date, days: int, staff_id: uuid.UUID | None
) -> list[BookingRow]:
    start_at = datetime.combine(start, time(0), tz)
    query = (
        _booking_query()
        .where(Booking.start_at >= start_at, Booking.start_at < start_at + timedelta(days=days))
        .order_by(Booking.start_at, Staff.name)
    )
    if staff_id:
        query = query.where(Booking.staff_id == staff_id)
    return [_booking_row(r, tz) for r in await db.execute(query)]


async def set_booking_status(db: AsyncSession, booking_id: uuid.UUID, new_status: str) -> None:
    booking = await db.get(Booking, booking_id)
    if booking is None:
        raise _not_found("Booking")
    if booking.status == "cancelled" and new_status != "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT, "This booking was cancelled")
    booking.status = new_status
    booking.updated_at = clock.now()
    await db.flush()


# Handoffs ---------------------------------------------------------------------------


async def handoffs(db: AsyncSession, tz: ZoneInfo, which: str) -> list[HandoffRow]:
    query = (
        select(Conversation, Customer.name, Customer.phone, User.name)
        .outerjoin(Customer, Customer.id == Conversation.customer_id)
        .outerjoin(User, User.id == Conversation.handoff_assignee_id)
        .where(Conversation.handoff)
        .order_by(
            Conversation.handoff_updated_at.desc().nulls_last(), Conversation.started_at.desc()
        )
        .limit(200)
    )
    if which == "active":
        query = query.where(Conversation.handoff_status.in_(["open", "claimed"]))
    elif which != "all":
        query = query.where(Conversation.handoff_status == which)
    rows = []
    for c, customer_name, phone, assignee in await db.execute(query):
        rows.append(
            HandoffRow(
                conversation_id=c.id,
                status=c.handoff_status or "open",
                reason=c.handoff_reason,
                summary=c.summary,
                channel=c.channel,
                customer_name=customer_name,
                customer_phone=phone,
                started_at=c.started_at.astimezone(tz),
                updated_at=c.handoff_updated_at.astimezone(tz) if c.handoff_updated_at else None,
                assignee=assignee,
                note=c.handoff_note,
            )
        )
    return rows


async def update_handoff(
    db: AsyncSession, conversation_id: uuid.UUID, user: User, action: str, note: str = ""
) -> None:
    c = await db.get(Conversation, conversation_id)
    if c is None or not c.handoff:
        raise _not_found("Handoff")
    if c.handoff_status == "resolved":
        raise HTTPException(status.HTTP_409_CONFLICT, "Already resolved")
    if action == "claim":
        c.handoff_status = "claimed"
        c.handoff_assignee_id = user.id
    else:
        c.handoff_status = "resolved"
        c.handoff_assignee_id = c.handoff_assignee_id or user.id
        c.handoff_note = note or None
    c.handoff_updated_at = clock.now()
    await db.flush()


# Conversations ------------------------------------------------------------------------


def _conversation_row(c: Conversation, name, phone, count, tz: ZoneInfo) -> dict:
    return {
        "id": c.id,
        "channel": c.channel,
        "language": c.language,
        "started_at": c.started_at.astimezone(tz),
        "duration_s": c.duration_s,
        "outcome": c.outcome,
        "handoff": c.handoff,
        "cost_inr": float(c.cost_inr or 0),
        "customer_name": name,
        "customer_phone": phone,
        "messages": count or 0,
    }


async def conversations(
    db: AsyncSession,
    tz: ZoneInfo,
    *,
    channel: str | None,
    outcome: str | None,
    limit: int,
    offset: int,
) -> ConversationsOut:
    counts = (
        select(Message.conversation_id, func.count().label("n"))
        .group_by(Message.conversation_id)
        .subquery()
    )
    query = (
        select(Conversation, Customer.name, Customer.phone, counts.c.n)
        .outerjoin(Customer, Customer.id == Conversation.customer_id)
        .outerjoin(counts, counts.c.conversation_id == Conversation.id)
    )
    if channel:
        query = query.where(Conversation.channel == channel)
    if outcome == "handoff":
        query = query.where(Conversation.handoff)
    elif outcome:
        query = query.where(Conversation.outcome == outcome)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = await db.execute(
        query.order_by(Conversation.started_at.desc()).limit(limit).offset(offset)
    )
    return ConversationsOut(
        total=total or 0,
        items=[ConversationRow(**_conversation_row(c, n, p, k, tz)) for c, n, p, k in rows],
    )


async def conversation_detail(
    db: AsyncSession, tz: ZoneInfo, conversation_id: uuid.UUID
) -> ConversationDetail:
    row = (
        await db.execute(
            select(Conversation, Customer.name, Customer.phone)
            .outerjoin(Customer, Customer.id == Conversation.customer_id)
            .where(Conversation.id == conversation_id)
        )
    ).one_or_none()
    if row is None:
        raise _not_found("Conversation")
    c, name, phone = row
    messages = (
        await db.scalars(
            select(Message).where(Message.conversation_id == c.id).order_by(Message.id)
        )
    ).all()
    return ConversationDetail(
        **_conversation_row(c, name, phone, len(messages), tz),
        summary=c.summary,
        handoff_reason=c.handoff_reason,
        llm_input_tokens=c.llm_input_tokens,
        llm_output_tokens=c.llm_output_tokens,
        transcript=[
            MessageRow(
                role=m.role,
                text=m.text,
                tool_name=m.tool_name,
                tool_args=m.tool_args,
                tool_result=m.tool_result,
                latency_ms=m.latency_ms,
                created_at=m.created_at.astimezone(tz),
            )
            for m in messages
        ],
    )


# Overview ----------------------------------------------------------------------------

VOICE_LATENCY_SQL = text(
    """
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY m.latency_ms) AS p50,
           percentile_cont(0.95) WITHIN GROUP (ORDER BY m.latency_ms) AS p95
    FROM messages m JOIN conversations c ON c.id = m.conversation_id
    WHERE c.channel = 'voice' AND m.role = 'assistant' AND m.latency_ms IS NOT NULL
      AND c.started_at >= :since
    """
)


async def overview(db: AsyncSession, business: Business) -> Overview:
    tz = ZoneInfo(business.timezone)
    now = clock.now()
    today = now.astimezone(tz).date()
    day_start = datetime.combine(today, time(0), tz)
    since = now - timedelta(days=7)

    bookings_today = await db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(
            Booking.start_at >= day_start,
            Booking.start_at < day_start + timedelta(days=1),
            Booking.status != "cancelled",
        )
    )
    upcoming = await db.execute(
        _booking_query()
        .where(Booking.status == "confirmed", Booking.start_at >= now)
        .order_by(Booking.start_at)
        .limit(5)
    )
    open_handoffs = await db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.handoff, Conversation.handoff_status.in_(["open", "claimed"]))
    )
    recent = Conversation.started_at >= since
    by_channel = dict(
        (
            await db.execute(
                select(Conversation.channel, func.count())
                .where(recent)
                .group_by(Conversation.channel)
            )
        ).all()
    )
    languages = dict(
        (
            await db.execute(
                select(Conversation.language, func.count())
                .where(recent, Conversation.language.is_not(None))
                .group_by(Conversation.language)
            )
        ).all()
    )
    cost = await db.scalar(select(func.coalesce(func.sum(Conversation.cost_inr), 0)).where(recent))
    agent_bookings = await db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(Booking.created_at >= since, Booking.source != "dashboard")
    )
    latency = (await db.execute(VOICE_LATENCY_SQL, {"since": since})).one()

    setup = {
        "services": bool(
            await db.scalar(select(func.count()).select_from(Service).where(Service.active))
        ),
        "hours": bool(await db.scalar(select(func.count()).select_from(WorkingHours))),
        "staff": bool(await db.scalar(select(func.count()).select_from(StaffService))),
        "faqs": bool(await db.scalar(select(func.count()).select_from(KbDocument))),
        "greeting": bool(business.greeting),
        "whatsapp": bool(business.whatsapp_phone_number_id),
    }
    return Overview(
        date=today,
        bookings_today=bookings_today or 0,
        next_bookings=[_booking_row(r, tz) for r in upcoming],
        open_handoffs=open_handoffs or 0,
        conversations_7d=sum(by_channel.values()),
        by_channel_7d=by_channel,
        agent_bookings_7d=agent_bookings or 0,
        cost_7d_inr=float(cost or Decimal(0)),
        voice_p50_ms=latency.p50,
        voice_p95_ms=latency.p95,
        languages_7d=languages,
        setup=setup,
    )


# Settings: business, hours, services, staff, blocked days -----------------------------


async def patch_business(db: AsyncSession, business: Business, body: BusinessPatch) -> BusinessOut:
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "languages" and not value:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Pick at least one language")
        setattr(business, field, value)
    await db.flush()
    return business_out(business)


async def get_hours(db: AsyncSession, staff_id: uuid.UUID | None) -> list[HoursRow]:
    owner = WorkingHours.staff_id == staff_id if staff_id else WorkingHours.staff_id.is_(None)
    rows = await db.scalars(
        select(WorkingHours).where(owner).order_by(WorkingHours.weekday, WorkingHours.open_time)
    )
    return [
        HoursRow(weekday=h.weekday, open_time=h.open_time, close_time=h.close_time) for h in rows
    ]


async def put_hours(
    db: AsyncSession, business: Business, staff_id: uuid.UUID | None, rows: list[HoursRow]
) -> list[HoursRow]:
    """Replace the weekly hours. For a staff member, an empty list means
    'same as the business hours'."""
    if staff_id and await db.get(Staff, staff_id) is None:
        raise _not_found("Staff member")
    for r in rows:
        if r.close_time <= r.open_time:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Closing time must be after opening time"
            )
    by_day: dict[int, list[HoursRow]] = {}
    for r in sorted(rows, key=lambda r: (r.weekday, r.open_time)):
        day = by_day.setdefault(r.weekday, [])
        if day and r.open_time < day[-1].close_time:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Opening hours overlap")
        day.append(r)
    owner = WorkingHours.staff_id == staff_id if staff_id else WorkingHours.staff_id.is_(None)
    await db.execute(delete(WorkingHours).where(owner))
    db.add_all(
        WorkingHours(
            business_id=business.id,
            staff_id=staff_id,
            weekday=r.weekday,
            open_time=r.open_time,
            close_time=r.close_time,
        )
        for r in rows
    )
    await db.flush()
    return await get_hours(db, staff_id)


def _service_row(s: Service) -> ServiceRow:
    return ServiceRow(
        id=s.id,
        name=s.name,
        duration_min=s.duration_min,
        price_inr=float(s.price_inr) if s.price_inr is not None else None,
        description=s.description,
        active=s.active,
    )


async def list_services(db: AsyncSession) -> list[ServiceRow]:
    rows = await db.scalars(select(Service).order_by(Service.active.desc(), Service.name))
    return [_service_row(s) for s in rows]


async def _flush_unique(db: AsyncSession, message: str) -> None:
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, message) from exc


async def create_service(db: AsyncSession, business: Business, body: ServiceIn) -> ServiceRow:
    service = Service(business_id=business.id, **body.model_dump())
    db.add(service)
    await _flush_unique(db, f"A service called {body.name!r} already exists")
    return _service_row(service)


async def patch_service(db: AsyncSession, service_id: uuid.UUID, body: ServicePatch) -> ServiceRow:
    service = await db.get(Service, service_id)
    if service is None:
        raise _not_found("Service")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(service, field, value)
    await _flush_unique(db, "Another service already has that name")
    return _service_row(service)


async def list_staff(db: AsyncSession) -> list[StaffRow]:
    staff = (await db.scalars(select(Staff).order_by(Staff.active.desc(), Staff.name))).all()
    links = (await db.execute(select(StaffService.staff_id, StaffService.service_id))).all()
    custom = set(
        (
            await db.scalars(
                select(WorkingHours.staff_id).where(WorkingHours.staff_id.is_not(None))
            )
        ).all()
    )
    return [
        StaffRow(
            id=s.id,
            name=s.name,
            active=s.active,
            service_ids=[svc for st, svc in links if st == s.id],
            custom_hours=s.id in custom,
        )
        for s in staff
    ]


async def _set_staff_services(
    db: AsyncSession, business: Business, staff_id: uuid.UUID, service_ids: list[uuid.UUID]
) -> None:
    known = set((await db.scalars(select(Service.id).where(Service.id.in_(service_ids)))).all())
    if unknown := set(service_ids) - known:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown services: {sorted(map(str, unknown))}"
        )
    await db.execute(delete(StaffService).where(StaffService.staff_id == staff_id))
    db.add_all(
        StaffService(business_id=business.id, staff_id=staff_id, service_id=sid) for sid in known
    )


async def create_staff(db: AsyncSession, business: Business, body: StaffIn) -> StaffRow:
    member = Staff(business_id=business.id, name=body.name)
    db.add(member)
    await db.flush()
    await _set_staff_services(db, business, member.id, body.service_ids)
    await db.flush()
    return next(s for s in await list_staff(db) if s.id == member.id)


async def patch_staff(
    db: AsyncSession, business: Business, staff_id: uuid.UUID, body: StaffPatch
) -> StaffRow:
    member = await db.get(Staff, staff_id)
    if member is None:
        raise _not_found("Staff member")
    if body.name is not None:
        member.name = body.name
    if body.active is not None:
        member.active = body.active
    if body.service_ids is not None:
        await _set_staff_services(db, business, staff_id, body.service_ids)
    await db.flush()
    return next(s for s in await list_staff(db) if s.id == staff_id)


async def list_blocked(db: AsyncSession, tz: ZoneInfo) -> list[BlockedRow]:
    today = datetime.combine(clock.now().astimezone(tz).date(), time(0), tz)
    rows = await db.execute(
        select(BlockedSlot, Staff.name)
        .outerjoin(Staff, Staff.id == BlockedSlot.staff_id)
        .where(BlockedSlot.end_at > today)
        .order_by(BlockedSlot.start_at)
    )
    return [
        BlockedRow(
            id=b.id,
            start_date=b.start_at.astimezone(tz).date(),
            end_date=(b.end_at.astimezone(tz) - timedelta(seconds=1)).date(),
            staff_id=b.staff_id,
            staff=name,
            reason=b.reason,
        )
        for b, name in rows
    ]


async def create_blocked(
    db: AsyncSession, business: Business, tz: ZoneInfo, body: BlockedIn
) -> list[BlockedRow]:
    if body.end_date < body.start_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "End date is before start date")
    if body.staff_id and await db.get(Staff, body.staff_id) is None:
        raise _not_found("Staff member")
    db.add(
        BlockedSlot(
            business_id=business.id,
            staff_id=body.staff_id,
            start_at=datetime.combine(body.start_date, time(0), tz),
            end_at=datetime.combine(body.end_date + timedelta(days=1), time(0), tz),
            reason=body.reason,
        )
    )
    await db.flush()
    return await list_blocked(db, tz)


async def delete_blocked(db: AsyncSession, blocked_id: uuid.UUID) -> None:
    if (await db.execute(delete(BlockedSlot).where(BlockedSlot.id == blocked_id))).rowcount == 0:
        raise _not_found("Blocked dates")


# Knowledge base (FAQs) --------------------------------------------------------------------


async def list_faqs(db: AsyncSession) -> list[FaqRow]:
    rows = await db.execute(
        select(KbDocument, func.string_agg(KbChunk.content, "\n\n"))
        .outerjoin(KbChunk, KbChunk.document_id == KbDocument.id)
        .group_by(KbDocument.id)
        .order_by(KbDocument.title)
    )
    return [
        FaqRow(id=d.id, title=d.title, content=content or "", uploaded_at=d.uploaded_at)
        for d, content in rows
    ]


async def save_faq(
    db: AsyncSession, business: Business, body: FaqIn, faq_id: uuid.UUID | None = None
) -> FaqRow:
    if faq_id:
        doc = await db.get(KbDocument, faq_id)
        if doc is None:
            raise _not_found("FAQ")
        doc.title = body.title
        await db.execute(delete(KbChunk).where(KbChunk.document_id == doc.id))
    else:
        doc = KbDocument(business_id=business.id, title=body.title, source_type="faq")
        db.add(doc)
        await db.flush()
    # One chunk per FAQ; the embeddings milestone will split long documents.
    db.add(KbChunk(business_id=business.id, document_id=doc.id, content=body.content))
    await db.flush()
    await db.refresh(doc)
    return FaqRow(id=doc.id, title=doc.title, content=body.content, uploaded_at=doc.uploaded_at)


async def delete_faq(db: AsyncSession, faq_id: uuid.UUID) -> None:
    if (await db.execute(delete(KbDocument).where(KbDocument.id == faq_id))).rowcount == 0:
        raise _not_found("FAQ")


# Team -------------------------------------------------------------------------------------


async def list_team(db: AsyncSession) -> list[UserOut]:
    rows = await db.scalars(select(User).order_by(User.role, User.name))
    return [user_out(u) for u in rows]


async def add_member(db: AsyncSession, business: Business, body: MemberIn) -> UserOut:
    user = User(
        business_id=business.id,
        email=body.email.lower(),
        name=body.name,
        role=body.role,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await _flush_unique(db, "That email already has a Vaani account")
    return user_out(user)


async def patch_member(
    db: AsyncSession, me: User, member_id: uuid.UUID, body: MemberPatch
) -> UserOut:
    member = await db.get(User, member_id)
    if member is None:
        raise _not_found("Team member")
    if member.id == me.id and (body.active is False or body.role == "staff"):
        raise HTTPException(status.HTTP_409_CONFLICT, "You can't remove or demote yourself")
    if body.active is not None:
        member.active = body.active
    if body.role is not None:
        member.role = body.role
    await db.flush()
    return user_out(member)

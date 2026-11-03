"""The dashboard API.

Both roles: who am I, bookings (view, add, mark done / no-show / cancelled, move),
and the handoff callback queue. Owner only: overview, conversations and
transcripts, settings (business, hours, services, staff, blocked dates), FAQs
and team. Each request runs in the signed-in user's business (row-level security).
"""

import datetime as dt
import uuid
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from app import clock
from app.auth import CurrentUser, DashboardDB, Owner, ViewerBusiness
from app.schemas import CreateBookingIn, RescheduleOrCancelIn
from app.schemas_dashboard import (
    BlockedIn,
    BlockedRow,
    BookingRow,
    BookingStatusIn,
    BusinessOut,
    BusinessPatch,
    ConversationDetail,
    ConversationsOut,
    FaqIn,
    FaqRow,
    HandoffRow,
    HoursRow,
    MemberIn,
    MemberPatch,
    MeOut,
    MoveBookingIn,
    NewBookingIn,
    Overview,
    ResolveIn,
    ServiceIn,
    ServicePatch,
    ServiceRow,
    StaffIn,
    StaffPatch,
    StaffRow,
    UserOut,
)
from app.services import bookings as booking_service
from app.services import dashboard as d

router = APIRouter(prefix="/v1/dashboard", tags=["dashboard"])


def tz(business) -> ZoneInfo:
    return ZoneInfo(business.timezone)


@router.get("/me")
async def me(user: CurrentUser, business: ViewerBusiness) -> MeOut:
    return MeOut(user=d.user_out(user), business=d.business_out(business))


# Bookings (owner and staff) -------------------------------------------------------------


@router.get("/bookings")
async def list_bookings(
    db: DashboardDB,
    business: ViewerBusiness,
    start: dt.date | None = None,
    days: Annotated[int, Query(ge=1, le=31)] = 1,
    staff_id: uuid.UUID | None = None,
) -> list[BookingRow]:
    start = start or clock.now().astimezone(tz(business)).date()
    return await d.bookings(db, tz(business), start=start, days=days, staff_id=staff_id)


@router.post("/bookings", status_code=201)
async def add_booking(body: NewBookingIn, db: DashboardDB, business: ViewerBusiness) -> dict:
    """A booking taken by the front desk, with the same checks as the agent's."""
    booking = await booking_service.create_booking(
        db, business, CreateBookingIn(**body.model_dump(), source="dashboard")
    )
    return {"id": str(booking.booking_id), "label": booking.label}


@router.post("/bookings/{booking_id}/status", status_code=204)
async def booking_status(
    booking_id: uuid.UUID, body: BookingStatusIn, db: DashboardDB, _: CurrentUser
) -> None:
    await d.set_booking_status(db, booking_id, body.status)


@router.post("/bookings/{booking_id}/move")
async def move_booking(
    booking_id: uuid.UUID, body: MoveBookingIn, db: DashboardDB, business: ViewerBusiness
) -> dict:
    moved = await booking_service.reschedule_or_cancel(
        db,
        business,
        RescheduleOrCancelIn(
            booking_id=booking_id, action="reschedule", new_start_at=body.start_at
        ),
    )
    return {"id": str(moved.booking_id), "label": moved.label}


# Handoffs (owner and staff) ---------------------------------------------------------------


@router.get("/handoffs")
async def list_handoffs(
    db: DashboardDB,
    business: ViewerBusiness,
    status: Literal["active", "open", "claimed", "resolved", "all"] = "active",
) -> list[HandoffRow]:
    return await d.handoffs(db, tz(business), status)


@router.post("/handoffs/{conversation_id}/claim", status_code=204)
async def claim_handoff(conversation_id: uuid.UUID, db: DashboardDB, user: CurrentUser) -> None:
    await d.update_handoff(db, conversation_id, user, "claim")


@router.post("/handoffs/{conversation_id}/resolve", status_code=204)
async def resolve_handoff(
    conversation_id: uuid.UUID, body: ResolveIn, db: DashboardDB, user: CurrentUser
) -> None:
    await d.update_handoff(db, conversation_id, user, "resolve", body.note)


# Owner: overview and conversations ----------------------------------------------------------


@router.get("/overview")
async def overview(db: DashboardDB, business: ViewerBusiness, _: Owner) -> Overview:
    return await d.overview(db, business)


@router.get("/conversations")
async def list_conversations(
    db: DashboardDB,
    business: ViewerBusiness,
    _: Owner,
    channel: Literal["voice", "whatsapp", "web_chat"] | None = None,
    outcome: Literal["booked", "changed", "handoff", "info"] | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConversationsOut:
    return await d.conversations(
        db, tz(business), channel=channel, outcome=outcome, limit=limit, offset=offset
    )


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID, db: DashboardDB, business: ViewerBusiness, _: Owner
) -> ConversationDetail:
    return await d.conversation_detail(db, tz(business), conversation_id)


# Owner: settings --------------------------------------------------------------------------


@router.patch("/business")
async def update_business(
    body: BusinessPatch, db: DashboardDB, business: ViewerBusiness, _: Owner
) -> BusinessOut:
    return await d.patch_business(db, business, body)


@router.get("/hours")
async def get_hours(db: DashboardDB, _: Owner, staff_id: uuid.UUID | None = None) -> list[HoursRow]:
    return await d.get_hours(db, staff_id)


@router.put("/hours")
async def put_hours(
    body: list[HoursRow],
    db: DashboardDB,
    business: ViewerBusiness,
    _: Owner,
    staff_id: uuid.UUID | None = None,
) -> list[HoursRow]:
    return await d.put_hours(db, business, staff_id, body)


@router.get("/services")
async def services(db: DashboardDB, _: CurrentUser) -> list[ServiceRow]:
    return await d.list_services(db)  # staff need these to add bookings


@router.post("/services", status_code=201)
async def create_service(
    body: ServiceIn, db: DashboardDB, business: ViewerBusiness, _: Owner
) -> ServiceRow:
    return await d.create_service(db, business, body)


@router.patch("/services/{service_id}")
async def update_service(
    service_id: uuid.UUID, body: ServicePatch, db: DashboardDB, _: Owner
) -> ServiceRow:
    return await d.patch_service(db, service_id, body)


@router.get("/staff")
async def staff(db: DashboardDB, _: CurrentUser) -> list[StaffRow]:
    return await d.list_staff(db)  # staff filter bookings by doctor


@router.post("/staff", status_code=201)
async def create_staff(
    body: StaffIn, db: DashboardDB, business: ViewerBusiness, _: Owner
) -> StaffRow:
    return await d.create_staff(db, business, body)


@router.patch("/staff/{staff_id}")
async def update_staff(
    staff_id: uuid.UUID, body: StaffPatch, db: DashboardDB, business: ViewerBusiness, _: Owner
) -> StaffRow:
    return await d.patch_staff(db, business, staff_id, body)


@router.get("/blocked")
async def blocked(db: DashboardDB, business: ViewerBusiness, _: Owner) -> list[BlockedRow]:
    return await d.list_blocked(db, tz(business))


@router.post("/blocked", status_code=201)
async def add_blocked(
    body: BlockedIn, db: DashboardDB, business: ViewerBusiness, _: Owner
) -> list[BlockedRow]:
    return await d.create_blocked(db, business, tz(business), body)


@router.delete("/blocked/{blocked_id}", status_code=204)
async def remove_blocked(blocked_id: uuid.UUID, db: DashboardDB, _: Owner) -> None:
    await d.delete_blocked(db, blocked_id)


# Owner: knowledge base and team -----------------------------------------------------------


@router.get("/faqs")
async def faqs(db: DashboardDB, _: Owner) -> list[FaqRow]:
    return await d.list_faqs(db)


@router.post("/faqs", status_code=201)
async def add_faq(body: FaqIn, db: DashboardDB, business: ViewerBusiness, _: Owner) -> FaqRow:
    return await d.save_faq(db, business, body)


@router.put("/faqs/{faq_id}")
async def edit_faq(
    faq_id: uuid.UUID, body: FaqIn, db: DashboardDB, business: ViewerBusiness, _: Owner
) -> FaqRow:
    return await d.save_faq(db, business, body, faq_id)


@router.delete("/faqs/{faq_id}", status_code=204)
async def remove_faq(faq_id: uuid.UUID, db: DashboardDB, _: Owner) -> None:
    await d.delete_faq(db, faq_id)


@router.get("/team")
async def team(db: DashboardDB, _: Owner) -> list[UserOut]:
    return await d.list_team(db)


@router.post("/team", status_code=201)
async def add_member(
    body: MemberIn, db: DashboardDB, business: ViewerBusiness, _: Owner
) -> UserOut:
    return await d.add_member(db, business, body)


@router.patch("/team/{member_id}")
async def update_member(
    member_id: uuid.UUID, body: MemberPatch, db: DashboardDB, owner: Owner
) -> UserOut:
    return await d.patch_member(db, owner, member_id, body)

"""The six tools the agent can call. The LLM never touches the database directly:
every action goes through here, scoped to one business by row-level security."""

from fastapi import APIRouter, Depends

from app.api.deps import CurrentBusiness, TenantDB, require_agent_key
from app.schemas import (
    AvailabilityOut,
    BookingOut,
    BookingsOut,
    CheckAvailabilityIn,
    CreateBookingIn,
    FindBookingIn,
    HandoffIn,
    HandoffOut,
    KnowledgeOut,
    RescheduleOrCancelIn,
    SearchKnowledgeIn,
)
from app.services import bookings, conversations, knowledge, scheduling

router = APIRouter(prefix="/v1/tools", tags=["tools"], dependencies=[Depends(require_agent_key)])


@router.post("/search_knowledge")
async def search_knowledge(
    body: SearchKnowledgeIn, db: TenantDB, _: CurrentBusiness
) -> KnowledgeOut:
    return await knowledge.search_knowledge(db, body.question)


@router.post("/check_availability")
async def check_availability(
    body: CheckAvailabilityIn, db: TenantDB, business: CurrentBusiness
) -> AvailabilityOut:
    return await scheduling.check_availability(db, business, body)


@router.post("/create_booking")
async def create_booking(
    body: CreateBookingIn, db: TenantDB, business: CurrentBusiness
) -> BookingOut:
    return await bookings.create_booking(db, business, body)


@router.post("/find_booking")
async def find_booking(body: FindBookingIn, db: TenantDB, business: CurrentBusiness) -> BookingsOut:
    return await bookings.find_bookings(db, business, body)


@router.post("/reschedule_or_cancel")
async def reschedule_or_cancel(
    body: RescheduleOrCancelIn, db: TenantDB, business: CurrentBusiness
) -> BookingOut:
    return await bookings.reschedule_or_cancel(db, business, body)


@router.post("/handoff_to_human")
async def handoff_to_human(body: HandoffIn, db: TenantDB, _: CurrentBusiness) -> HandoffOut:
    return await conversations.handoff(db, body)

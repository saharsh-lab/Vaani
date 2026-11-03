"""Endpoints the agent runtime uses around a conversation: which business it is
serving, the facts for the system prompt, and the transcript log."""

import uuid
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app import clock
from app.api.deps import CurrentBusiness, TenantDB, require_agent_key
from app.db import system_session
from app.errors import NotFound
from app.models import Business, Service, Staff, WorkingHours
from app.schemas import (
    AgentContextOut,
    BusinessRef,
    ConversationOut,
    EndConversationIn,
    HoursInfo,
    ResumeConversationIn,
    ResumedConversationOut,
    ServiceInfo,
    StartConversationIn,
    TurnIn,
)
from app.services import conversations

router = APIRouter(prefix="/v1", tags=["agent"], dependencies=[Depends(require_agent_key)])


@router.get("/businesses/{slug}")
async def business_by_slug(slug: str) -> BusinessRef:
    # Runs before a tenant is known, so it uses the system connection.
    async with system_session() as session:
        business = await session.scalar(select(Business).where(Business.slug == slug))
    if business is None:
        raise NotFound(f"No business with slug {slug!r}.")
    return BusinessRef(id=business.id, slug=business.slug, name=business.name)


@router.get("/agent/context")
async def agent_context(db: TenantDB, business: CurrentBusiness) -> AgentContextOut:
    services = await db.scalars(select(Service).where(Service.active).order_by(Service.name))
    hours = await db.scalars(
        select(WorkingHours)
        .where(WorkingHours.staff_id.is_(None))
        .order_by(WorkingHours.weekday, WorkingHours.open_time)
    )
    staff = await db.scalars(select(Staff.name).where(Staff.active).order_by(Staff.name))
    return AgentContextOut(
        id=business.id,
        name=business.name,
        type=business.type,
        timezone=business.timezone,
        languages=business.languages,
        greeting=business.greeting,
        address=business.address,
        phone=business.phone,
        now_local=clock.now().astimezone(ZoneInfo(business.timezone)),
        services=[
            ServiceInfo(
                name=s.name,
                duration_min=s.duration_min,
                price_inr=float(s.price_inr) if s.price_inr is not None else None,
                description=s.description,
            )
            for s in services
        ],
        hours=[
            HoursInfo(weekday=h.weekday, open_time=h.open_time, close_time=h.close_time)
            for h in hours
        ],
        staff=list(staff),
    )


@router.post("/conversations")
async def start_conversation(
    body: StartConversationIn, db: TenantDB, business: CurrentBusiness
) -> ConversationOut:
    return await conversations.start(db, business, body)


@router.post("/conversations/resume")
async def resume_conversation(
    body: ResumeConversationIn, db: TenantDB, business: CurrentBusiness
) -> ResumedConversationOut:
    return await conversations.resume(db, business, body)


@router.post("/conversations/{conversation_id}/turns")
async def record_turn(
    conversation_id: uuid.UUID, body: TurnIn, db: TenantDB, business: CurrentBusiness
) -> dict:
    return {"saved": await conversations.record_turn(db, business, conversation_id, body)}


@router.post("/conversations/{conversation_id}/end")
async def end_conversation(
    conversation_id: uuid.UUID, body: EndConversationIn, db: TenantDB, _: CurrentBusiness
) -> dict:
    await conversations.end(db, conversation_id, body)
    return {"ok": True}

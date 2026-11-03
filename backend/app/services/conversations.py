"""Conversation records: one per call or chat, with the full transcript.

Totals (tokens, cost, outcome) are updated after every turn, so the dashboard is
accurate even for chats that are still open.
"""

import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.errors import InvalidRequest, NotFound
from app.models import Business, Conversation, Customer, Message
from app.phones import InvalidPhone, mask_phone, normalize_phone
from app.schemas import (
    ConversationOut,
    EndConversationIn,
    HandoffIn,
    HandoffOut,
    ResumeConversationIn,
    ResumedConversationOut,
    StartConversationIn,
    TurnIn,
)

log = logging.getLogger(__name__)


async def _get(session: AsyncSession, conversation_id: uuid.UUID) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFound("No such conversation.")
    return conversation


async def _customer(
    session: AsyncSession, business: Business, raw_phone: str, language: str | None
) -> tuple[str, uuid.UUID]:
    try:
        phone = normalize_phone(raw_phone)
    except InvalidPhone as exc:
        raise InvalidRequest("customer_phone is not a valid phone number.") from exc
    stmt = pg_insert(Customer).values(
        id=uuid.uuid4(), business_id=business.id, phone=phone, preferred_language=language
    )
    customer_id = await session.scalar(
        stmt.on_conflict_do_update(
            index_elements=[Customer.business_id, Customer.phone],
            set_={"phone": stmt.excluded.phone},  # no-op update so RETURNING gives the id
        ).returning(Customer.id)
    )
    return phone, customer_id


async def _create(
    session: AsyncSession,
    business: Business,
    channel: str,
    customer_id: uuid.UUID | None,
    language: str | None,
) -> Conversation:
    now = clock.now()
    conversation = Conversation(
        business_id=business.id,
        customer_id=customer_id,
        channel=channel,
        language=language,
        started_at=now,
        last_activity_at=now,
    )
    session.add(conversation)
    await session.flush()
    return conversation


def _close(conversation: Conversation, at: datetime) -> None:
    conversation.ended_at = at
    conversation.duration_s = int((at - conversation.started_at).total_seconds())
    conversation.agent_state = None  # the transcript is in messages; drop the LLM copy


async def start(
    session: AsyncSession, business: Business, body: StartConversationIn
) -> ConversationOut:
    phone = customer_id = None
    if body.customer_phone:
        phone, customer_id = await _customer(session, business, body.customer_phone, body.language)
    conversation = await _create(session, business, body.channel, customer_id, body.language)
    log.info(
        "conversation %s started on %s from %s", conversation.id, body.channel, mask_phone(phone)
    )
    return ConversationOut(id=conversation.id, customer_phone=phone)


async def resume(
    session: AsyncSession, business: Business, body: ResumeConversationIn
) -> ResumedConversationOut:
    """Continue the customer's open conversation on this channel if it was active
    within idle_minutes; otherwise close it and start a new one."""
    phone, customer_id = await _customer(session, business, body.customer_phone, None)
    current = await session.scalar(
        select(Conversation)
        .where(
            Conversation.customer_id == customer_id,
            Conversation.channel == body.channel,
            Conversation.ended_at.is_(None),
        )
        .order_by(Conversation.started_at.desc())
        .limit(1)
        .with_for_update()
    )
    if current and clock.now() - current.last_activity_at < timedelta(minutes=body.idle_minutes):
        return ResumedConversationOut(
            id=current.id, customer_phone=phone, resumed=True, agent_state=current.agent_state
        )
    if current:
        _close(current, at=current.last_activity_at)
    conversation = await _create(session, business, body.channel, customer_id, None)
    log.info(
        "conversation %s started on %s from %s", conversation.id, body.channel, mask_phone(phone)
    )
    return ResumedConversationOut(
        id=conversation.id, customer_phone=phone, resumed=False, agent_state=None
    )


async def record_turn(
    session: AsyncSession, business: Business, conversation_id: uuid.UUID, body: TurnIn
) -> int:
    conversation = await _get(session, conversation_id)
    if body.messages:
        await session.execute(
            insert(Message),
            [
                {"business_id": business.id, "conversation_id": conversation_id, **m.model_dump()}
                for m in body.messages
            ],
        )
    conversation.last_activity_at = clock.now()
    conversation.outcome = body.outcome or conversation.outcome
    conversation.llm_input_tokens = body.llm_input_tokens
    conversation.llm_output_tokens = body.llm_output_tokens
    conversation.cost_inr = Decimal(str(round(body.cost_inr, 4)))
    conversation.language = body.language or conversation.language
    if body.agent_state is not None:
        conversation.agent_state = body.agent_state
    await session.flush()
    return len(body.messages)


async def end(session: AsyncSession, conversation_id: uuid.UUID, body: EndConversationIn) -> None:
    conversation = await _get(session, conversation_id)
    _close(conversation, at=clock.now())
    conversation.outcome = body.outcome or conversation.outcome
    conversation.summary = body.summary or conversation.summary
    conversation.language = body.language or conversation.language
    await session.flush()


async def handoff(session: AsyncSession, body: HandoffIn) -> HandoffOut:
    if body.conversation_id:
        conversation = await _get(session, body.conversation_id)
        conversation.handoff = True
        conversation.handoff_reason = body.reason
        conversation.summary = body.summary
        conversation.handoff_status = "open"
        conversation.handoff_updated_at = clock.now()
        await session.flush()
    # TODO(notifications milestone): message the owner on WhatsApp (needs an approved template).
    log.warning("handoff requested (conversation %s): %s", body.conversation_id, body.reason)
    return HandoffOut(
        ok=True,
        message="The team has been notified and will call the customer back soon.",
    )

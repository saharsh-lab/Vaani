"""ORM mappings for the columns the API uses.

The schema itself (constraints, row-level security, indexes) is hand-written SQL
in migrations/versions; keep the two in step when adding columns.
"""

import uuid
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import ARRAY, BigInteger, DateTime, Identity, Numeric, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True), str: Text, dict: JSONB}


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


class Business(Base):
    __tablename__ = "businesses"
    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str]
    name: Mapped[str]
    type: Mapped[str]
    timezone: Mapped[str] = mapped_column(default="Asia/Kolkata")
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text), default=lambda: ["en"])
    greeting: Mapped[str | None]
    agent_voice: Mapped[str | None]
    plan: Mapped[str] = mapped_column(default="free")
    phone: Mapped[str | None]
    address: Mapped[str | None]
    whatsapp_phone_number_id: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID]
    email: Mapped[str]
    name: Mapped[str | None]
    role: Mapped[str]  # owner | staff
    password_hash: Mapped[str | None]
    active: Mapped[bool] = mapped_column(default=True)
    last_login_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Service(Base):
    __tablename__ = "services"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID]
    name: Mapped[str]
    description: Mapped[str | None]
    duration_min: Mapped[int]
    price_inr: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    active: Mapped[bool] = mapped_column(default=True)


class Staff(Base):
    __tablename__ = "staff"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID]
    name: Mapped[str]
    active: Mapped[bool] = mapped_column(default=True)


class StaffService(Base):
    __tablename__ = "staff_services"
    staff_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    service_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    business_id: Mapped[uuid.UUID]


class WorkingHours(Base):
    __tablename__ = "working_hours"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID]
    staff_id: Mapped[uuid.UUID | None]
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0 = Monday
    open_time: Mapped[time]
    close_time: Mapped[time]


class BlockedSlot(Base):
    __tablename__ = "blocked_slots"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID]
    staff_id: Mapped[uuid.UUID | None]
    start_at: Mapped[datetime]
    end_at: Mapped[datetime]
    reason: Mapped[str | None]


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID]
    name: Mapped[str | None]
    phone: Mapped[str]
    preferred_language: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID]
    customer_id: Mapped[uuid.UUID]
    service_id: Mapped[uuid.UUID]
    staff_id: Mapped[uuid.UUID]
    conversation_id: Mapped[uuid.UUID | None]
    start_at: Mapped[datetime]
    end_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(default="confirmed")
    source: Mapped[str]
    customer_name: Mapped[str | None]
    notes: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class KbDocument(Base):
    __tablename__ = "kb_documents"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID]
    title: Mapped[str]
    source_type: Mapped[str]
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())


class KbChunk(Base):
    __tablename__ = "kb_chunks"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID]
    content: Mapped[str]
    # embedding (pgvector) and tsv (generated) are read with SQL in services/knowledge.py.


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID]
    customer_id: Mapped[uuid.UUID | None]
    channel: Mapped[str]
    language: Mapped[str | None]
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]
    duration_s: Mapped[int | None]
    outcome: Mapped[str | None]
    handoff: Mapped[bool] = mapped_column(default=False)
    handoff_reason: Mapped[str | None]
    summary: Mapped[str | None]
    llm_input_tokens: Mapped[int] = mapped_column(default=0)
    llm_output_tokens: Mapped[int] = mapped_column(default=0)
    cost_inr: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    recording_url: Mapped[str | None]
    last_activity_at: Mapped[datetime]
    agent_state: Mapped[dict | None]  # serialized LLM history, for channels like WhatsApp
    handoff_status: Mapped[str | None]  # open | claimed | resolved
    handoff_assignee_id: Mapped[uuid.UUID | None]
    handoff_note: Mapped[str | None]
    handoff_updated_at: Mapped[datetime | None]


class ChannelEvent(Base):
    """An inbound message id already accepted from a channel (for dedupe)."""

    __tablename__ = "channel_events"
    business_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(primary_key=True)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    business_id: Mapped[uuid.UUID]
    conversation_id: Mapped[uuid.UUID]
    role: Mapped[str]
    text: Mapped[str | None]
    tool_name: Mapped[str | None]
    tool_args: Mapped[dict | None]
    tool_result: Mapped[dict | None]
    latency_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

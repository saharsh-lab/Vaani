"""Request and response bodies. Tool inputs mirror the tool declarations the LLM
sees (vaani_agent/tools.py), plus fields the agent runtime fills in itself."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

Channel = Literal["voice", "whatsapp", "web_chat"]


# Tools -------------------------------------------------------------------


class SearchKnowledgeIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class KnowledgeHit(BaseModel):
    title: str
    content: str


class KnowledgeOut(BaseModel):
    results: list[KnowledgeHit]
    note: str | None = None


class CheckAvailabilityIn(BaseModel):
    service: str
    date: dt.date
    preferred_time: str | None = Field(
        default=None, description="morning, afternoon, evening, any, or a time such as 18:15"
    )
    staff: str | None = None


class Slot(BaseModel):
    start_at: dt.datetime
    label: str
    staff: str


class AvailabilityOut(BaseModel):
    service: str
    duration_min: int
    price_inr: float | None
    date: dt.date
    slots: list[Slot]
    note: str | None = None


class CreateBookingIn(BaseModel):
    service: str
    start_at: dt.datetime = Field(description="Local time if no offset is given")
    customer_name: str = Field(min_length=1, max_length=100)
    phone: str
    staff: str | None = None
    # Filled by the agent runtime, not the LLM:
    source: Literal["voice", "whatsapp", "web_chat", "dashboard"] = "web_chat"
    conversation_id: uuid.UUID | None = None


class BookingOut(BaseModel):
    booking_id: uuid.UUID
    service: str
    staff: str
    start_at: dt.datetime
    label: str
    status: str
    customer_name: str | None


class FindBookingIn(BaseModel):
    phone: str


class BookingsOut(BaseModel):
    bookings: list[BookingOut]


class RescheduleOrCancelIn(BaseModel):
    booking_id: uuid.UUID
    action: Literal["reschedule", "cancel"]
    new_start_at: dt.datetime | None = None
    # Set by the runtime when the caller's number is verified (WhatsApp, phone line):
    # the booking must then belong to that number.
    caller_phone: str | None = None


class HandoffIn(BaseModel):
    reason: str = Field(max_length=300)
    summary: str = Field(max_length=2000)
    conversation_id: uuid.UUID | None = None


class HandoffOut(BaseModel):
    ok: bool
    message: str


# Conversations -----------------------------------------------------------


class StartConversationIn(BaseModel):
    channel: Channel
    customer_phone: str | None = None
    language: str | None = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    customer_phone: str | None


class ResumeConversationIn(BaseModel):
    channel: Channel
    customer_phone: str
    idle_minutes: int = Field(default=30, ge=1, le=24 * 60)


class ResumedConversationOut(ConversationOut):
    resumed: bool
    agent_state: dict | None


class MessageIn(BaseModel):
    role: Literal["user", "assistant", "tool"]
    text: str | None = None
    tool_name: str | None = None
    tool_args: dict | None = None
    tool_result: dict | None = None
    latency_ms: int | None = None


class TurnIn(BaseModel):
    """One exchange: the transcript lines plus running totals for the conversation."""

    messages: list[MessageIn]
    outcome: str | None = None
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    cost_inr: float = 0
    language: str | None = None  # e.g. te-IN, when speech-to-text detected it
    agent_state: dict | None = None  # only channels that resume later send this


class EndConversationIn(BaseModel):
    outcome: str | None = None
    summary: str | None = None
    language: str | None = None


# Agent context -------------------------------------------------------------


class BusinessRef(BaseModel):
    id: uuid.UUID
    slug: str
    name: str


class ServiceInfo(BaseModel):
    name: str
    duration_min: int
    price_inr: float | None
    description: str | None


class HoursInfo(BaseModel):
    weekday: int
    open_time: dt.time
    close_time: dt.time


class AgentContextOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    timezone: str
    languages: list[str]
    greeting: str | None
    address: str | None
    phone: str | None
    now_local: dt.datetime
    services: list[ServiceInfo]
    hours: list[HoursInfo]
    staff: list[str]

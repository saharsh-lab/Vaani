"""Request and response bodies for the owner and staff dashboard."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.phones import InvalidPhone, normalize_phone

Role = Literal["owner", "staff"]


# Auth ---------------------------------------------------------------------------


class SignupIn(BaseModel):
    business_name: str = Field(min_length=2, max_length=80)
    business_type: str = Field(min_length=2, max_length=60, description="e.g. dental clinic, salon")
    languages: list[Literal["te", "hi", "en", "ta", "kn"]] = ["en"]
    owner_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    name: str | None
    email: str
    role: Role
    active: bool = True


class BusinessOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    type: str
    timezone: str
    languages: list[str]
    greeting: str | None
    address: str | None
    phone: str | None
    whatsapp_connected: bool


class MeOut(BaseModel):
    user: UserOut
    business: BusinessOut


# Bookings -----------------------------------------------------------------------


class BookingRow(BaseModel):
    id: uuid.UUID
    start_at: dt.datetime
    end_at: dt.datetime
    status: str
    source: str
    service: str
    staff: str
    staff_id: uuid.UUID
    customer_name: str | None
    customer_phone: str
    conversation_id: uuid.UUID | None


class NewBookingIn(BaseModel):
    service: str
    start_at: dt.datetime
    customer_name: str = Field(min_length=1, max_length=100)
    phone: str
    staff: str | None = None


class BookingStatusIn(BaseModel):
    status: Literal["completed", "no_show", "cancelled"]


class MoveBookingIn(BaseModel):
    start_at: dt.datetime


# Handoffs and conversations -------------------------------------------------------


class HandoffRow(BaseModel):
    conversation_id: uuid.UUID
    status: Literal["open", "claimed", "resolved"]
    reason: str | None
    summary: str | None
    channel: str
    customer_name: str | None
    customer_phone: str | None
    started_at: dt.datetime
    updated_at: dt.datetime | None
    assignee: str | None
    note: str | None


class ResolveIn(BaseModel):
    note: str = Field(default="", max_length=1000)


class ConversationRow(BaseModel):
    id: uuid.UUID
    channel: str
    language: str | None
    started_at: dt.datetime
    duration_s: int | None
    outcome: str | None
    handoff: bool
    cost_inr: float
    customer_name: str | None
    customer_phone: str | None
    messages: int


class ConversationsOut(BaseModel):
    total: int
    items: list[ConversationRow]


class MessageRow(BaseModel):
    role: str
    text: str | None
    tool_name: str | None
    tool_args: dict | None
    tool_result: dict | None
    latency_ms: int | None
    created_at: dt.datetime


class ConversationDetail(ConversationRow):
    summary: str | None
    handoff_reason: str | None
    llm_input_tokens: int
    llm_output_tokens: int
    transcript: list[MessageRow]


# Overview -------------------------------------------------------------------------


class Overview(BaseModel):
    date: dt.date
    bookings_today: int
    next_bookings: list[BookingRow]
    open_handoffs: int
    conversations_7d: int
    by_channel_7d: dict[str, int]
    agent_bookings_7d: int
    cost_7d_inr: float
    voice_p50_ms: float | None
    voice_p95_ms: float | None
    languages_7d: dict[str, int]
    setup: dict[str, bool]  # onboarding checklist: what's done


# Settings -------------------------------------------------------------------------


class BusinessPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    type: str | None = Field(default=None, min_length=2, max_length=60)
    greeting: str | None = Field(default=None, max_length=300)
    address: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    languages: list[Literal["te", "hi", "en", "ta", "kn"]] | None = None

    @field_validator("phone")
    @classmethod
    def _real_phone(cls, value: str | None) -> str | None:
        # Shown as a tap-to-call link on the booking page, so it must be a number.
        if not value:
            return value
        try:
            return normalize_phone(value)
        except InvalidPhone:
            raise ValueError(
                "Enter a phone number, like 040 2345 6789 or +91 98765 43210"
            ) from None


class HoursRow(BaseModel):
    weekday: int = Field(ge=0, le=6)  # 0 = Monday
    open_time: dt.time
    close_time: dt.time


class ServiceRow(BaseModel):
    id: uuid.UUID
    name: str
    duration_min: int
    price_inr: float | None
    description: str | None
    active: bool


class ServiceIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    duration_min: int = Field(ge=5, le=480)
    price_inr: float | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=300)


class ServicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    duration_min: int | None = Field(default=None, ge=5, le=480)
    price_inr: float | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=300)
    active: bool | None = None


class StaffRow(BaseModel):
    id: uuid.UUID
    name: str
    active: bool
    service_ids: list[uuid.UUID]
    custom_hours: bool


class StaffIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    service_ids: list[uuid.UUID] = []


class StaffPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    active: bool | None = None
    service_ids: list[uuid.UUID] | None = None


class BlockedRow(BaseModel):
    id: uuid.UUID
    start_date: dt.date
    end_date: dt.date
    staff_id: uuid.UUID | None
    staff: str | None
    reason: str | None


class BlockedIn(BaseModel):
    start_date: dt.date
    end_date: dt.date
    staff_id: uuid.UUID | None = None
    reason: str | None = Field(default=None, max_length=120)


class FaqRow(BaseModel):
    id: uuid.UUID
    title: str
    content: str  # an uploaded document is shortened to a preview
    source_type: str  # faq | pdf | text
    chunks: int
    uploaded_at: dt.datetime


class FaqIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    content: str = Field(min_length=2, max_length=4000)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class MemberIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200, description="Temporary; share it privately")
    role: Role = "staff"


class MemberPatch(BaseModel):
    active: bool | None = None
    role: Role | None = None

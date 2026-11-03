"""Eval datasets: scripted conversations and labelled single utterances.

Every eval runs with the clock frozen at NOW, against a fresh copy of the demo
clinic (app/seed.py), so "tomorrow evening at 6" always means the same slot.
"""

from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 2, 9, 0, tzinfo=IST)  # Monday; the clinic opens at 10
HERE = Path(__file__).parent

Category = Literal[
    "booking", "reschedule", "cancel", "faq", "off_topic", "angry", "language_switch"
]
BOOKING_CATEGORIES = {"booking", "reschedule", "cancel"}


def local(when: str) -> datetime:
    """'2026-11-03 18:00' in clinic time."""
    return datetime.strptime(when, "%Y-%m-%d %H:%M").replace(tzinfo=IST)


class Turn(BaseModel):
    text: str
    voice: str | None = None  # e.g. te-IN: send as a transcribed WhatsApp voice note


class SetupBooking(BaseModel):
    """A booking that exists before the conversation starts."""

    service: str
    start: str
    mine: bool = True  # the caller's own booking, or another customer's
    name: str = "Existing Customer"


class ExpectedBooking(BaseModel):
    service: str
    start: str
    staff: str | None = None  # substring of the staff member's name


class Move(BaseModel):
    from_: str = Field(alias="from")
    to: str


class Expect(BaseModel):
    booking: ExpectedBooking | None = None  # exactly one new booking like this
    rescheduled: Move | None = None  # the caller's booking at `from` now starts at `to`
    cancelled: list[str] = []  # the caller's bookings at these times are cancelled
    unchanged: list[str] = []  # the caller's bookings at these times are untouched
    handoff: bool | None = None
    tools: list[str] = []  # each must be called at least once
    forbid_tools: list[str] = []
    judge: str | None = None  # rubric the LLM judge checks the transcript against

    @property
    def changes_bookings(self) -> bool:
        return bool(self.booking or self.rescheduled or self.cancelled)


class Scenario(BaseModel):
    id: str
    category: Category
    language: str
    channel: Literal["whatsapp", "web_chat"] = "whatsapp"  # WhatsApp numbers are verified
    phone: str = "9876543210"  # the caller's number (what they say, on web chat)
    setup: list[SetupBooking] = []
    turns: list[Turn]
    expect: Expect

    @field_validator("turns", mode="before")
    @classmethod
    def _plain_turns(cls, turns: list) -> list:
        return [{"text": t} if isinstance(t, str) else t for t in turns]


class Utterance(BaseModel):
    """One customer message, labelled with the first tool the agent should call."""

    id: str
    lang: str
    text: str
    tool: str  # a tool name, or "none" for a direct answer
    args: dict = {}  # expected subset of the tool's arguments
    keywords: list[str] = []  # for search_knowledge: the question mentions one of these
    also_ok: list[str] = []  # other acceptable first tools ("none" allowed)

    @model_validator(mode="after")
    def _known_tool(self) -> "Utterance":
        from vaani_agent.tools import TOOL_NAMES

        for name in [self.tool, *self.also_ok]:
            if name != "none" and name not in TOOL_NAMES:
                raise ValueError(f"{self.id}: unknown tool {name}")
        return self


def load_scenarios(path: Path = HERE / "scenarios.yaml") -> list[Scenario]:
    scenarios = [Scenario.model_validate(s) for s in yaml.safe_load(path.read_text())]
    ids = [s.id for s in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate scenario ids")
    return scenarios


def load_utterances(path: Path = HERE / "tool_calls.yaml") -> list[Utterance]:
    utterances = [Utterance.model_validate(u) for u in yaml.safe_load(path.read_text())]
    ids = [u.id for u in utterances]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate utterance ids")
    return utterances

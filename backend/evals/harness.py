"""Runs scenarios and utterances through the real agent, API and database.

Each scenario gets its own copy of the demo clinic (a separate tenant), so
scenarios can run in parallel without seeing each other's bookings. Results
are judged on what actually happened in the database, not on wording.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.db import system_session
from app.main import app
from app.models import Booking, Conversation, Customer, Service, Staff
from app.phones import normalize_phone
from app.seed import seed_demo
from app.services.availability import parse_preference
from evals.dataset import IST, Scenario, Utterance, local
from evals.llm import WAITED, is_capacity_error
from vaani_agent.api_client import VaaniApi
from vaani_agent.config import AgentSettings
from vaani_agent.runtime import AgentSession, VoiceNote
from vaani_agent.tools import ToolContext

OTHER_CUSTOMER_PHONE = "+919000000001"


class RecordingApi(VaaniApi):
    """The agent's API client, plus a log of every tool call it makes."""

    def __init__(self, business_id: str) -> None:
        super().__init__(
            "http://vaani.eval",
            get_settings().agent_api_key,
            business_id,
            transport=httpx.ASGITransport(app=app),
        )
        self.tool_log: list[dict] = []

    async def call_tool(self, name: str, args: dict) -> dict:
        result = await super().call_tool(name, args)
        self.tool_log.append({"name": name, "args": args, "result": result})
        return result


@dataclass
class TurnRecord:
    user: str
    reply: str
    tools: list[dict]
    latency_ms: int


@dataclass
class ConversationResult:
    scenario: Scenario
    turns: list[TurnRecord] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    handoff: bool = False
    cost_inr: float = 0.0
    system_prompt: str = ""
    rubric: dict | None = None  # {"pass": bool, "reason": str} from the judge
    unsupported_claims: list[list[str]] = field(default_factory=list)  # per reply
    error: str | None = None
    not_scored: bool = False  # Gemini quota/overload, not the agent's doing

    @property
    def passed(self) -> bool:
        rubric_ok = self.rubric is None or self.rubric.get("pass", False)
        return not self.failures and not self.error and rubric_ok


@dataclass
class UtteranceResult:
    utterance: Utterance
    passed: bool
    first_tool: str  # "none" if the agent answered without a tool
    args: dict
    mismatches: list[str]
    reply: str = ""
    error: str | None = None
    not_scored: bool = False  # Gemini quota/overload, not the agent's doing


async def new_tenant(slug_hint: str) -> uuid.UUID:
    slug = ("ev-" + slug_hint)[:40].rstrip("-")
    async with system_session() as session:
        return await seed_demo(session, slug=slug)


# Conversations -------------------------------------------------------------------


async def _apply_setup(api: VaaniApi, scenario: Scenario) -> dict[str, str]:
    """Create pre-existing bookings; returns {start: booking_id} for the caller's."""
    mine = {}
    for b in scenario.setup:
        result = await api.call_tool(
            "create_booking",
            {
                "service": b.service,
                "start_at": local(b.start).isoformat(),
                "customer_name": b.name,
                "phone": scenario.phone if b.mine else OTHER_CUSTOMER_PHONE,
                "source": "dashboard",
            },
        )
        if "error" in result:
            raise RuntimeError(f"setup booking {b} failed: {result}")
        if b.mine:
            mine[b.start] = result["booking_id"]
    return mine


async def run_conversation(
    scenario: Scenario, index: int, *, llm, settings: AgentSettings
) -> ConversationResult:
    result = ConversationResult(scenario)
    business_id = await new_tenant(f"{index:02d}-{scenario.id}")
    async with RecordingApi(str(business_id)) as api:
        setup = await _apply_setup(api, scenario)
        api.tool_log.clear()
        verified = scenario.channel == "whatsapp"
        conversation = await api.start_conversation(
            scenario.channel, customer_phone=scenario.phone if verified else None
        )
        session = AgentSession(
            api=api,
            llm=llm,
            settings=settings,
            context=await api.context(),
            tool_context=ToolContext(
                conversation["id"],
                scenario.channel,
                verified_phone=conversation["customer_phone"] if verified else None,
            ),
        )
        result.system_prompt = session.system_prompt
        try:
            for turn in scenario.turns:
                before, started = len(api.tool_log), time.perf_counter()
                voice = VoiceNote(turn.voice, 0, 0.0) if turn.voice else None
                waited = [0.0]
                token = WAITED.set(waited)
                try:
                    reply = await session.reply(turn.text, voice=voice)
                finally:
                    WAITED.reset(token)
                elapsed = time.perf_counter() - started - waited[0]
                result.turns.append(
                    TurnRecord(turn.text, reply, api.tool_log[before:], int(elapsed * 1000))
                )
            await session.end()
        except Exception as exc:  # a crash is a failed scenario, not a failed run
            result.error = short_error(exc)
            result.not_scored = is_capacity_error(exc)
        result.cost_inr = session.cost_inr
        result.failures = await check(
            scenario, business_id, conversation["id"], setup, api.tool_log
        )
        async with system_session() as s:
            row = await s.get(Conversation, uuid.UUID(conversation["id"]))
            result.handoff = bool(row and row.handoff)
    return result


async def check(
    scenario: Scenario,
    business_id: uuid.UUID,
    conversation_id: str,
    setup: dict[str, str],
    tool_log: list[dict],
) -> list[str]:
    """What should be true in the database (and the tool log) after the conversation."""
    expect = scenario.expect
    failures: list[str] = []
    async with system_session() as s:
        rows = (
            await s.execute(
                select(Booking, Service.name, Staff.name, Customer.phone)
                .join(Service, Service.id == Booking.service_id)
                .join(Staff, Staff.id == Booking.staff_id)
                .join(Customer, Customer.id == Booking.customer_id)
                .where(Booking.business_id == business_id)
            )
        ).all()
        conversation = await s.get(Conversation, uuid.UUID(conversation_id))

    setup_ids = set(setup.values())
    by_id = {str(b.id): (b, svc, staff, phone) for b, svc, staff, phone in rows}
    new = [r for bid, r in by_id.items() if bid not in setup_ids and r[3] != OTHER_CUSTOMER_PHONE]

    def describe(row) -> str:
        b, svc, staff, _ = row
        return f"{svc} {b.start_at.astimezone(IST):%a %d %b %H:%M} ({b.status})"

    def mine_at(start: str):
        return by_id[setup[start]]

    if expect.booking:
        e = expect.booking
        want = local(e.start)
        matches = [
            r
            for r in new
            if r[0].status == "confirmed" and r[1] == e.service and r[0].start_at == want
        ]
        if not matches:
            got = ", ".join(describe(r) for r in new) or "no new booking"
            failures.append(f"expected {e.service} at {e.start}; got {got}")
        else:
            b, _, staff, phone = matches[0]
            if e.staff and e.staff.lower() not in staff.lower():
                failures.append(f"booked with {staff}, expected {e.staff}")
            if phone != normalize_phone(scenario.phone):
                failures.append(f"booked under {phone}, expected {normalize_phone(scenario.phone)}")
        if len(new) > 1:
            failures.append(f"{len(new)} bookings created: " + ", ".join(describe(r) for r in new))
    elif new:
        failures.append("unexpected booking: " + ", ".join(describe(r) for r in new))

    moved_from = expect.rescheduled.from_ if expect.rescheduled else None
    if expect.rescheduled:
        b = mine_at(moved_from)[0]
        if b.status != "confirmed" or b.start_at != local(expect.rescheduled.to):
            failures.append(
                f"expected booking moved to {expect.rescheduled.to}; it's {describe(mine_at(moved_from))}"
            )

    for start in expect.cancelled:
        if mine_at(start)[0].status != "cancelled":
            failures.append(
                f"expected booking at {start} cancelled; it's {describe(mine_at(start))}"
            )

    # Every other booking the caller had must be untouched.
    for start in set(setup) - set(expect.cancelled) - {moved_from}:
        b = mine_at(start)[0]
        if b.status != "confirmed" or b.start_at != local(start):
            failures.append(
                f"booking at {start} should be untouched; it's {describe(mine_at(start))}"
            )

    if expect.handoff is not None and bool(conversation and conversation.handoff) != expect.handoff:
        failures.append("expected a handoff" if expect.handoff else "unexpected handoff")

    called = {t["name"] for t in tool_log}
    failures += [f"never called {t}" for t in expect.tools if t not in called]
    failures += [f"called {t}, which it shouldn't" for t in expect.forbid_tools if t in called]
    return failures


# Single utterances (tool-call accuracy) -----------------------------------------------


def match_args(tool: str, expected: dict, actual: dict) -> list[str]:
    mismatches = []
    for key, want in expected.items():
        got = actual.get(key)
        if key == "preferred_time":
            ok = _same_time(str(want), got)
        elif key == "staff":
            ok = isinstance(got, str) and str(want).lower() in got.lower()
        elif isinstance(want, str):
            ok = isinstance(got, str) and got.strip().lower() == want.lower()
        else:
            ok = got == want
        if not ok:
            mismatches.append(f"{key}: expected {want!r}, got {got!r}")
    return mismatches


def _same_time(want: str, got) -> bool:
    try:
        expected = parse_preference(want)
        actual = parse_preference(got if isinstance(got, str) else None)
    except ValueError:
        return False
    if expected.target is not None:
        return actual.target == expected.target
    if expected.window is not None:
        if actual.window == expected.window:
            return True
        lo, hi = expected.window
        return actual.target is not None and lo <= actual.target < hi
    return True


def score_utterance(utterance: Utterance, tool_log: list[dict], reply: str) -> UtteranceResult:
    first = tool_log[0] if tool_log else None
    name = first["name"] if first else "none"
    args = first["args"] if first else {}
    mismatches: list[str] = []
    if name == utterance.tool:
        mismatches = match_args(name, utterance.args, args)
        if utterance.keywords:
            question = str(args.get("question", "")).lower()
            if not any(k.lower() in question for k in utterance.keywords):
                mismatches.append(f"question {question!r} mentions none of {utterance.keywords}")
    elif name not in utterance.also_ok:
        mismatches.append(f"expected {utterance.tool}, got {name}")
    return UtteranceResult(utterance, not mismatches, name, args, mismatches, reply)


async def run_utterance(
    utterance: Utterance, business_id: uuid.UUID, *, llm, settings: AgentSettings
) -> UtteranceResult:
    async with RecordingApi(str(business_id)) as api:
        conversation = await api.start_conversation("whatsapp", customer_phone="9876543210")
        session = AgentSession(
            api=api,
            llm=llm,
            settings=settings,
            context=await api.context(),
            tool_context=ToolContext(
                conversation["id"], "whatsapp", verified_phone=conversation["customer_phone"]
            ),
        )
        try:
            reply = await session.reply(utterance.text)
        except Exception as exc:
            return UtteranceResult(
                utterance,
                False,
                "error",
                {},
                [],
                error=short_error(exc),
                not_scored=is_capacity_error(exc),
            )
        return score_utterance(utterance, api.tool_log, reply)


async def gather_limited(coros, limit: int) -> list:
    semaphore = asyncio.Semaphore(limit)

    async def run(coro):
        async with semaphore:
            return await coro

    return await asyncio.gather(*(run(c) for c in coros))


def turn_latencies(results: list[ConversationResult]) -> list[int]:
    return [t.latency_ms for r in results for t in r.turns]


def short_error(exc: Exception) -> str:
    message = " ".join(str(exc).split())
    return f"{type(exc).__name__}: {message[:160]}{'…' if len(message) > 160 else ''}"


def now_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

"""The agent loop with a scripted model standing in for Gemini, calling the real
API. This is the seed of the conversation eval suite."""

import httpx
import pytest
from sqlalchemy import func, select

from app.db import system_session
from app.main import app
from app.models import Conversation, Message
from tests.fakes import ScriptedModel, model_calls, model_says
from vaani_agent.api_client import VaaniApi
from vaani_agent.config import AgentSettings
from vaani_agent.prompt import build_system_prompt, summarize_hours
from vaani_agent.runtime import FALLBACK_REPLY, AgentSession
from vaani_agent.tools import ToolContext, prepare_args


def api_for(business_id) -> VaaniApi:
    return VaaniApi(
        "http://vaani.internal",
        "test-key",
        business_id=str(business_id),
        transport=httpx.ASGITransport(app=app),
    )


async def test_agent_books_a_slot_through_the_tools(clinic):
    async with api_for(clinic) as api:
        context = await api.context()
        conversation = await api.start_conversation("whatsapp", customer_phone="9876543210")
        model = ScriptedModel(
            [
                model_calls(
                    "check_availability",
                    service="RCT consultation",
                    date="2026-11-03",
                    preferred_time="evening",
                ),
                model_says("Repu 5:00, 5:30 leda 6:00 available undi. Edi convenient?"),
                model_calls(
                    "create_booking",
                    service="RCT consultation",
                    start_at="2026-11-03T18:00:00+05:30",
                    customer_name="Ravi",
                    phone="0000000000",  # wrong: the verified WhatsApp number must win
                ),
                model_says("Repu sayantram 6 ki booked."),
            ]
        )
        session = AgentSession(
            api=api,
            llm=model,
            settings=AgentSettings(),
            context=context,
            tool_context=ToolContext(
                conversation["id"], "whatsapp", verified_phone=conversation["customer_phone"]
            ),
        )

        reply = await session.reply("Repu evening root canal consultation ki appointment kavali")
        assert reply.startswith("Repu 5:00")
        tool_result = model.requests[1][-1].parts[0].function_response
        assert tool_result.name == "check_availability"
        assert len(tool_result.response["slots"]) == 3

        assert (
            await session.reply("6 ki book cheyandi, naa peru Ravi")
            == "Repu sayantram 6 ki booked."
        )
        await session.end()

        found = await api.call_tool("find_booking", {"phone": "9876543210"})
        assert found["bookings"][0]["label"] == "Tue 3 Nov, 6:00 PM"

    async with system_session() as s:
        row = await s.get(Conversation, conversation["id"])
        logged = await s.scalar(
            select(func.count()).select_from(Message).where(Message.conversation_id == row.id)
        )
    assert row.outcome == "booked"
    assert row.llm_input_tokens == 4000 and row.llm_output_tokens == 80
    assert float(row.cost_inr) > 0
    assert logged == 6  # user, tool, assistant for each of the two turns


async def test_tool_errors_reach_the_model_instead_of_crashing(clinic):
    async with api_for(clinic) as api:
        result = await api.call_tool(
            "check_availability", {"service": "Hair cut", "date": "2026-11-03"}
        )
        assert result["error"] == "invalid_request"
        assert "Teeth cleaning" in result["services"]

        result = await api.call_tool("check_availability", {"service": "RCT consultation"})
        assert result["error"] == "invalid_arguments" and "date" in result["message"]


def test_runtime_overrides_fields_the_model_must_not_control():
    ctx = ToolContext("conv-1", "whatsapp", verified_phone="+919876543210")
    args = prepare_args("find_booking", {"phone": "+911111111111"}, ctx)
    assert args == {"phone": "+919876543210"}
    args = prepare_args("create_booking", {"phone": "1", "service": "x"}, ctx)
    assert args["phone"] == "+919876543210" and args["source"] == "whatsapp"
    assert args["conversation_id"] == "conv-1"
    assert prepare_args("reschedule_or_cancel", {}, ctx)["caller_phone"] == "+919876543210"


def test_hours_summary_groups_days():
    hours = [
        {"weekday": d, "open_time": o, "close_time": c}
        for d in range(6)
        for o, c in (("10:00:00", "13:30:00"), ("17:00:00", "21:00:00"))
    ]
    assert summarize_hours(hours) == ["Mon-Sat: 10:00 AM-1:30 PM, 5:00 PM-9:00 PM", "Sun: closed"]


async def test_system_prompt_carries_business_facts(client):
    context = (await client.get("/v1/agent/context")).json()
    prompt = build_system_prompt(context, channel="voice", verified_phone=None)
    assert "Sri Dental Clinic" in prompt
    assert "- RCT consultation: 30 min, ₹500" in prompt
    assert "Monday, 02 November 2026" in prompt
    assert "Mon-Sat: 10:00 AM-1:30 PM, 5:00 PM-9:00 PM" in prompt
    assert "Ask for their mobile number" in prompt


async def scripted_session(api: VaaniApi, model: ScriptedModel) -> AgentSession:
    context = await api.context()
    conversation = await api.start_conversation("web_chat")
    return AgentSession(
        api=api,
        llm=model,
        settings=AgentSettings(),
        context=context,
        tool_context=ToolContext(conversation["id"], "web_chat"),
    )


async def test_failed_model_call_leaves_history_clean(clinic):
    async with api_for(clinic) as api:
        session = await scripted_session(api, ScriptedModel([RuntimeError("model down")]))
        with pytest.raises(RuntimeError):
            await session.reply("hello")
        assert session.history == []


async def test_empty_answer_falls_back_and_keeps_turns_alternating(clinic):
    async with api_for(clinic) as api:
        session = await scripted_session(api, ScriptedModel([model_says(""), model_says("Hi!")]))
        assert await session.reply("hello") == FALLBACK_REPLY
        assert [c.role for c in session.history] == ["user", "model"]
        assert await session.reply("hello again") == "Hi!"
        assert [c.role for c in session.history] == ["user", "model", "user", "model"]


async def test_prompt_lists_dates_and_confirmation_rules(client):
    context = (await client.get("/v1/agent/context")).json()
    prompt = build_system_prompt(context, channel="whatsapp", verified_phone="+919876543210")
    assert "- Tue 03 Nov = 2026-11-03 (tomorrow)" in prompt
    assert "- Thu 05 Nov = 2026-11-05 (this Thursday)" in prompt
    assert "- Mon 09 Nov = 2026-11-09 (next Monday)" in prompt
    assert "never book, cancel or change a booking in the same reply" in prompt
    assert "answer those directly" in prompt

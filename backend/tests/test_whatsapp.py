"""WhatsApp channel end to end: signed webhooks in, the real API and database,
a scripted model in place of Gemini, and a fake Graph API capturing replies."""

import asyncio
import hashlib
import hmac
import json
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select, update

from app import clock
from app.db import system_session
from app.main import app
from app.models import Booking, Business, Conversation, Message
from tests.conftest import NOW
from tests.fakes import ScriptedModel, model_calls, model_says, ogg_opus
from vaani_agent.api_client import VaaniApi
from vaani_agent.config import AgentSettings
from vaani_agent.speech import SarvamSTT
from vaani_agent.whatsapp import (
    ERROR_REPLY,
    UNSUPPORTED_REPLY,
    VOICE_NOT_UNDERSTOOD_REPLY,
    VOICE_TOO_LONG_REPLY,
    WhatsAppAgent,
    WhatsAppClient,
    parse_webhook,
    verify_signature,
)

NUMBER_ID = "106540352242922"
SENDER = "919876543210"


def webhook(text=None, *, msg_id="wamid.1", kind="text", number_id=NUMBER_ID) -> dict:
    message = {"from": SENDER, "id": msg_id, "timestamp": "1793600000", "type": kind}
    if kind == "text":
        message["text"] = {"body": text}
    elif kind == "audio":
        message["audio"] = {"id": "media-1", "mime_type": "audio/ogg; codecs=opus", "voice": True}
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15550001111", "phone_number_id": number_id},
        "contacts": [{"profile": {"name": "Ravi"}, "wa_id": SENDER}],
        "messages": [message],
    }
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": value}]}],
    }


async def post(client, payload: dict, secret: str = "test-secret") -> httpx.Response:
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # ASGITransport waits for background tasks, so the agent turn is done on return.
    return await client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
    )


MEDIA_URL = "https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid=media-1"


@pytest.fixture
async def wa(clinic):
    """The demo clinic answering NUMBER_ID, with a scripted model, a fake Graph API
    (messages and media) and a fake Sarvam speech-to-text."""
    async with system_session() as s:
        await s.execute(
            update(Business).where(Business.id == clinic).values(whatsapp_phone_number_id=NUMBER_ID)
        )
    state = SimpleNamespace(
        sent=[],
        audio=ogg_opus(8),
        file_size=None,  # override to fake what Meta reports
        media_downloads=0,
        stt_requests=[],
        stt_response=httpx.Response(
            200,
            json={"transcript": "repu evening RCT consultation kavali", "language_code": "te-IN"},
        ),
    )

    def graph_api(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        if request.url.host == "lookaside.fbsbx.com":
            state.media_downloads += 1
            return httpx.Response(200, content=state.audio, headers={"Content-Type": "audio/ogg"})
        if request.url.path == "/v23.0/media-1":
            size = state.file_size if state.file_size is not None else len(state.audio)
            return httpx.Response(
                200,
                json={
                    "url": MEDIA_URL,
                    "mime_type": "audio/ogg",
                    "file_size": size,
                    "id": "media-1",
                },
            )
        assert request.url.path == f"/v23.0/{NUMBER_ID}/messages"
        state.sent.append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.out"}]})

    def sarvam(request: httpx.Request) -> httpx.Response:
        state.stt_requests.append(request.content)
        return state.stt_response

    state.model = ScriptedModel([])
    app.state.whatsapp_agent = WhatsAppAgent(
        settings=AgentSettings(whatsapp_graph_version="v23.0", whatsapp_idle_minutes=30),
        llm=state.model,
        whatsapp=WhatsAppClient("test-token", "v23.0", transport=httpx.MockTransport(graph_api)),
        api_for=lambda bid: VaaniApi(
            "http://vaani.internal", "test-key", bid, transport=httpx.ASGITransport(app=app)
        ),
        stt=SarvamSTT("sk-test", transport=httpx.MockTransport(sarvam)),
    )
    state.replies = lambda: [m["text"]["body"] for m in state.sent if m.get("type") == "text"]
    yield state
    del app.state.whatsapp_agent


async def conversations_of_sender() -> list[Conversation]:
    async with system_session() as s:
        rows = await s.scalars(
            select(Conversation)
            .where(Conversation.channel == "whatsapp")
            .order_by(Conversation.started_at)
        )
        return list(rows.all())


# Webhook security -----------------------------------------------------------


async def test_subscription_handshake(client):
    params = {"hub.mode": "subscribe", "hub.verify_token": "test-verify", "hub.challenge": "42"}
    r = await client.get("/webhooks/whatsapp", params=params)
    assert r.status_code == 200 and r.text == "42"
    r = await client.get("/webhooks/whatsapp", params={**params, "hub.verify_token": "nope"})
    assert r.status_code == 403


async def test_unsigned_or_forged_webhooks_are_rejected(client, wa):
    r = await post(client, webhook("hi"), secret="attacker")
    assert r.status_code == 403
    r = await client.post("/webhooks/whatsapp", json=webhook("hi"))
    assert r.status_code == 403
    assert wa.model.requests == [] and wa.sent == []


def test_signature_check():
    body = b'{"a":1}'
    good = "sha256=" + hmac.new(b"s", body, hashlib.sha256).hexdigest()
    assert verify_signature("s", body, good)
    assert not verify_signature("s", body + b" ", good)
    assert not verify_signature("s", body, None)


# Conversations --------------------------------------------------------------


async def test_booking_across_two_messages(client, wa):
    wa.model.responses += [
        model_calls(
            "check_availability",
            service="RCT consultation",
            date="2026-11-03",
            preferred_time="evening",
        ),
        model_says("Namaskaram! Repu 5:00, 5:30 leda 6:00 undi. Edi kavali?"),
        model_calls(
            "create_booking",
            service="RCT consultation",
            start_at="2026-11-03T18:00:00+05:30",
            customer_name="Ravi",
            phone="0000000000",  # wrong: the sender's WhatsApp number must be used
        ),
        model_says("Booked: Tue 3 Nov, 6:00 PM."),
    ]

    r = await post(client, webhook("Repu evening RCT consultation kavali", msg_id="wamid.1"))
    assert r.json() == {"accepted": 1}
    assert wa.replies() == ["Namaskaram! Repu 5:00, 5:30 leda 6:00 undi. Edi kavali?"]
    assert wa.sent[0] == {  # marked read, with typing indicator, before replying
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": "wamid.1",
        "typing_indicator": {"type": "text"},
    }

    await post(client, webhook("6 ki, naa peru Ravi", msg_id="wamid.2"))
    assert wa.replies()[-1] == "Booked: Tue 3 Nov, 6:00 PM."

    # The second message continued the first: history restored, tool call included.
    second_turn = wa.model.requests[2]
    assert [c.role for c in second_turn] == ["user", "model", "user", "model", "user"]
    assert second_turn[1].parts[0].function_call.name == "check_availability"

    async with system_session() as s:
        booking = await s.scalar(select(Booking))
    assert booking.source == "whatsapp"
    (conversation,) = await conversations_of_sender()
    assert conversation.outcome == "booked" and conversation.ended_at is None
    assert conversation.llm_input_tokens == 4000
    assert booking.conversation_id == conversation.id

    found = await client.post("/v1/tools/find_booking", json={"phone": "+" + SENDER})
    assert found.json()["bookings"][0]["label"] == "Tue 3 Nov, 6:00 PM"


async def test_redelivered_message_is_handled_once(client, wa):
    wa.model.responses += [model_says("Hello!")]
    assert (await post(client, webhook("hi"))).json() == {"accepted": 1}
    assert (await post(client, webhook("hi"))).json() == {"accepted": 0}
    assert len(wa.model.requests) == 1 and wa.replies() == ["Hello!"]


async def test_quick_messages_are_handled_in_order(client, wa):
    wa.model.responses += [model_says("first"), model_says("second")]
    await asyncio.gather(
        post(client, webhook("hi", msg_id="wamid.a")),
        post(client, webhook("are you open today?", msg_id="wamid.b")),
    )
    # Without the per-customer lock, both turns would start from an empty history.
    assert [len(r) for r in wa.model.requests] == [1, 3]
    assert len(await conversations_of_sender()) == 1


async def test_long_gap_starts_a_new_conversation(client, wa, monkeypatch):
    wa.model.responses += [model_says("Hello!"), model_says("Hello again!")]
    await post(client, webhook("hi", msg_id="wamid.1"))
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(minutes=45))
    await post(client, webhook("hi", msg_id="wamid.2"))

    assert len(wa.model.requests[1]) == 1  # fresh history
    old, new = await conversations_of_sender()
    assert old.ended_at == NOW and old.agent_state is None
    assert new.ended_at is None and new.agent_state is not None


async def test_voice_note_without_speech_to_text_asks_to_type(client, wa):
    app.state.whatsapp_agent.stt = None
    await post(client, webhook(kind="audio"))
    assert wa.replies() == [UNSUPPORTED_REPLY]
    assert wa.model.requests == [] and wa.media_downloads == 0


async def test_model_failure_apologises_and_next_message_recovers(client, wa):
    wa.model.responses += [RuntimeError("Gemini down"), model_says("Hello!")]
    await post(client, webhook("hi", msg_id="wamid.1"))
    await post(client, webhook("hi again", msg_id="wamid.2"))
    assert wa.replies() == [ERROR_REPLY, "Hello!"]
    assert len(wa.model.requests[1]) == 1  # the failed turn left no half-saved history


async def test_unknown_number_and_status_updates_are_ignored(client, wa):
    assert (await post(client, webhook("hi", number_id="999"))).json() == {"accepted": 0}
    statuses = webhook("hi")
    value = statuses["entry"][0]["changes"][0]["value"]
    value["statuses"] = [{"id": "wamid.out", "status": "delivered"}]
    del value["messages"]
    assert (await post(client, statuses)).json() == {"accepted": 0}
    assert wa.sent == []


async def test_failed_deliveries_are_logged_with_metas_reason(client, wa, caplog):
    report = webhook("hi")
    value = report["entry"][0]["changes"][0]["value"]
    del value["messages"]
    value["statuses"] = [
        {"id": "wamid.out1", "status": "delivered", "recipient_id": "919876543210"},
        {
            "id": "wamid.out2",
            "status": "failed",
            "recipient_id": "919876543210",
            "errors": [
                {
                    "code": 131030,
                    "title": "Recipient phone number not in allowed list",
                    "error_data": {"details": "Add the number to the allowed list"},
                }
            ],
        },
    ]
    with caplog.at_level("INFO", logger="app.api.whatsapp"):
        assert (await post(client, report)).json() == {"accepted": 0}
    lines = [r.getMessage() for r in caplog.records if r.name == "app.api.whatsapp"]
    assert "WhatsApp reply to +91******3210: delivered" in lines
    assert any("131030 Recipient phone number not in allowed list" in line for line in lines)
    assert not any("9876543210" in line for line in lines)  # numbers stay masked


def test_parses_button_and_list_replies():
    payload = webhook("x")
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    message.update(type="interactive", interactive={"list_reply": {"id": "1", "title": "6:15 PM"}})
    (parsed,) = parse_webhook(payload)
    assert parsed.text == "6:15 PM"
    assert parsed.sender_phone == "+919876543210" and parsed.profile_name == "Ravi"


# Voice notes ----------------------------------------------------------------


async def test_voice_note_is_transcribed_and_answered(client, wa):
    wa.model.responses += [model_says("Repu sayantram 5:00 ki slot undi.")]
    await post(client, webhook(kind="audio"))

    assert wa.replies() == ["Repu sayantram 5:00 ki slot undi."]
    sent_to_model = wa.model.requests[0][-1].parts[0].text
    assert sent_to_model == "[voice note, te-IN] repu evening RCT consultation kavali"
    # The recogniser was primed with this business's names.
    assert b"RCT consultation" in wa.stt_requests[0]
    assert b"Dr. Lakshmi Reddy" in wa.stt_requests[0]

    (conversation,) = await conversations_of_sender()
    assert conversation.language == "te-IN"
    s = AgentSettings()
    llm = (
        (1000 * s.llm_input_usd_per_million + 20 * s.llm_output_usd_per_million)
        / 1e6
        * s.usd_to_inr
    )
    speech = 8 / 3600 * 29.40  # 8-second voice note
    assert float(conversation.cost_inr) == pytest.approx(llm + speech, abs=1e-4)
    async with system_session() as s:
        user_message = await s.scalar(select(Message).where(Message.role == "user"))
    assert user_message.text.startswith("[voice note, te-IN]")
    assert user_message.latency_ms is not None  # transcription time


async def test_voice_note_over_30_seconds_is_declined_before_transcribing(client, wa):
    wa.audio = ogg_opus(45)
    await post(client, webhook(kind="audio"))
    assert wa.replies() == [VOICE_TOO_LONG_REPLY]
    assert wa.stt_requests == [] and wa.model.requests == []


async def test_huge_audio_file_is_not_downloaded(client, wa):
    wa.file_size = 10_000_000
    await post(client, webhook(kind="audio"))
    assert wa.replies() == [VOICE_TOO_LONG_REPLY]
    assert wa.media_downloads == 0


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(422, json={"error": {"message": "Invalid audio"}}),
        httpx.Response(503, json={"error": {"message": "Overloaded"}}),
        httpx.Response(200, json={"transcript": "", "language_code": None}),
    ],
)
async def test_unusable_transcription_asks_to_resend(client, wa, response):
    wa.stt_response = response
    await post(client, webhook(kind="audio"))
    assert wa.replies() == [VOICE_NOT_UNDERSTOOD_REPLY]
    assert wa.model.requests == []


async def test_voice_and_text_mix_in_one_conversation(client, wa):
    wa.model.responses += [model_says("5:00 PM undi."), model_says("Sare, booking cheddam.")]
    await post(client, webhook(kind="audio", msg_id="wamid.v1"))
    await post(client, webhook("ok 5 ki", msg_id="wamid.t2"))
    second_turn = wa.model.requests[1]
    assert second_turn[0].parts[0].text.startswith("[voice note, te-IN]")
    assert second_turn[-1].parts[0].text == "ok 5 ki"
    (conversation,) = await conversations_of_sender()
    assert conversation.language == "te-IN"  # kept after a text message

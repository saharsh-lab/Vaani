"""Browser voice calls: the token endpoint and widget page, and the LiveKit voice
agent driven through LiveKit's own AgentSession in text mode with a scripted LLM
(the same tool and session code a real call runs, minus audio)."""

import json
from types import SimpleNamespace

import httpx
import pytest
from livekit import api as livekit
from livekit.agents import AgentSession, ErrorEvent, llm
from livekit.agents.metrics import AgentSessionUsage, LLMModelUsage, STTModelUsage, TTSModelUsage
from sqlalchemy import select

import app.api.voice as voice_api
from app.db import system_session
from app.main import app
from app.models import Booking, Conversation, Message
from tests.fakes import ScriptedLiveKitLLM
from vaani_agent.api_client import VaaniApi
from vaani_agent.config import VOICE_AGENT_NAME, AgentSettings, get_agent_settings
from vaani_agent.prompt import build_system_prompt, voice_greeting_instructions
from vaani_agent.tools import ToolContext
from vaani_agent.voice import (
    ONE_MOMENT,
    SAY_AGAIN,
    CallRecorder,
    StockPhrases,
    VaaniVoiceAgent,
    livekit_tools,
    tts_language,
    tts_voice,
    voice_llm,
)


@pytest.fixture(autouse=True)
def fresh_rate_limit(monkeypatch):
    monkeypatch.setattr(voice_api, "limiter", voice_api.RateLimiter())


def api_for(business_id) -> VaaniApi:
    return VaaniApi(
        "http://vaani.internal",
        "test-key",
        str(business_id),
        transport=httpx.ASGITransport(app=app),
    )


# Token endpoint and widget page ----------------------------------------------


async def test_session_token_sends_the_voice_agent_with_the_business(client, clinic):
    r = await client.post("/v1/voice/session", json={"business": "sri-dental"})
    assert r.status_code == 200, r.text
    body = r.json()
    settings = get_agent_settings()
    assert body["server_url"] == (settings.livekit_public_url or settings.livekit_url)

    claims = livekit.TokenVerifier(settings.livekit_api_key, settings.livekit_api_secret).verify(
        body["participant_token"]
    )
    assert claims.identity.startswith("caller-")
    assert claims.video.room == body["room_name"] and claims.video.room_join
    assert body["room_name"].startswith("call-sri-dental-")
    (dispatch,) = claims.room_config.agents
    assert dispatch.agent_name == VOICE_AGENT_NAME
    assert json.loads(dispatch.metadata) == {"business_id": str(clinic)}


async def test_each_call_gets_its_own_room(client, clinic):
    rooms = {
        (await client.post("/v1/voice/session", json={"business": "sri-dental"})).json()[
            "room_name"
        ]
        for _ in range(3)
    }
    assert len(rooms) == 3


async def test_unknown_business_gets_no_token(client, clinic):
    r = await client.post("/v1/voice/session", json={"business": "nope"})
    assert r.status_code == 404


async def test_calls_are_rate_limited_per_ip(client, clinic, monkeypatch):
    monkeypatch.setattr(get_agent_settings(), "voice_calls_per_ip_per_hour", 2)
    codes = [
        (await client.post("/v1/voice/session", json={"business": "sri-dental"})).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]


async def test_widget_page(client, clinic):
    r = await client.get("/voice/sri-dental")
    assert r.status_code == 200
    assert "<title>Talk to Sri Dental Clinic</title>" in r.text
    assert 'const SLUG = "sri-dental";' in r.text
    assert "livekit-client@2.22.4" in r.text
    assert (await client.get("/voice/nope")).status_code == 404


# The voice agent ----------------------------------------------------------------


async def test_voice_agent_books_and_records_the_call(clinic):
    async with api_for(clinic) as api:
        context = await api.context()
        conversation = await api.start_conversation("voice")
        recorder = CallRecorder(api, AgentSettings(), conversation["id"])
        model = ScriptedLiveKitLLM(
            [
                (
                    "check_availability",
                    {
                        "service": "RCT consultation",
                        "date": "2026-11-03",
                        "preferred_time": "evening",
                    },
                ),
                "రేపు సాయంత్రం 5, 5:30 లేదా 6 కి slot ఉంది.",
                (
                    "create_booking",
                    {
                        "service": "RCT consultation",
                        "start_at": "2026-11-03T18:00:00+05:30",
                        "customer_name": "Ravi",
                        "phone": "98765 43210",
                    },
                ),
                "రేపు సాయంత్రం 6 కి booked.",
            ]
        )
        async with AgentSession(llm=model) as session:
            recorder.attach(session)
            # With "one moment" spoken from inside the tools, as on a real call.
            phrases = StockPhrases(session, "te-IN")
            tools = livekit_tools(
                api, ToolContext(conversation["id"], "voice"), recorder, phrases.one_moment
            )
            await session.start(VaaniVoiceAgent(context, tools))

            first = await session.run(user_input="రేపు evening RCT consultation కావాలి")
            first.expect.next_event().is_function_call(name="check_availability")
            output = first.expect.next_event().is_function_call_output()
            assert len(json.loads(output.event().item.output)["slots"]) == 3
            first.expect.next_event().is_message(role="assistant")

            second = await session.run(user_input="6 కి, నా పేరు Ravi, number 98765 43210")
            second.expect.next_event().is_function_call(name="create_booking")
            second.expect.next_event().is_function_call_output()
            second.expect.next_event().is_message(role="assistant")

        assert model.requests[0].items[0].role == "system"  # the business's voice prompt
        await recorder.finish("test")

    async with system_session() as s:
        booking = await s.scalar(select(Booking))
        call = await s.get(Conversation, conversation["id"])
        roles = (
            await s.scalars(
                select(Message.role).where(Message.conversation_id == call.id).order_by(Message.id)
            )
        ).all()
    assert booking.source == "voice" and booking.conversation_id == call.id
    assert call.channel == "voice" and call.outcome == "booked" and call.ended_at is not None
    assert roles == ["user", "tool", "assistant", "user", "tool", "assistant"]


async def test_tool_errors_are_spoken_about_not_crashed_on(clinic):
    async with api_for(clinic) as api:
        conversation = await api.start_conversation("voice")
        recorder = CallRecorder(api, AgentSettings(), conversation["id"])
        tools = {
            t.info.name: t
            for t in livekit_tools(api, ToolContext(conversation["id"], "voice"), recorder)
        }
        result = json.loads(
            await tools["check_availability"](
                raw_arguments={"service": "Hair cut", "date": "2026-11-03"}
            )
        )
    assert result["error"] == "invalid_request" and "Teeth cleaning" in result["services"]
    assert recorder.outcomes == set()


# Call recorder: latency, language, cost -------------------------------------------


class FakeApi:
    def __init__(self, fail_first: bool = False):
        self.turns: list[dict] = []
        self.fail_first = fail_first
        self.http = SimpleNamespace(aclose=self._noop)
        self.ended = None

    async def _noop(self):
        pass

    async def save_turn(self, conversation_id, **turn):
        if self.fail_first:
            self.fail_first = False
            raise httpx.ConnectError("api down")
        self.turns.append(turn)

    async def end_conversation(self, conversation_id, **fields):
        self.ended = fields


def said(role: str, text: str, e2e: float | None = None):
    metrics = {"e2e_latency": e2e} if e2e is not None else {}
    return SimpleNamespace(item=llm.ChatMessage(role=role, content=[text], metrics=metrics))


async def test_recorder_saves_each_reply_with_its_latency():
    fake = FakeApi()
    recorder = CallRecorder(fake, AgentSettings(), "conv-1")
    recorder._item_added(said("user", "hello"))
    recorder._item_added(said("assistant", "Namaskaram!", e2e=0.84))
    await recorder.finish()
    assert fake.turns[0]["messages"] == [
        {"role": "user", "text": "hello"},
        {"role": "assistant", "text": "Namaskaram!", "latency_ms": 840},
    ]
    assert recorder.latencies_ms == [840]
    assert fake.ended == {"outcome": "info"}


async def test_recorder_keeps_lines_when_saving_fails_and_retries():
    fake = FakeApi(fail_first=True)
    recorder = CallRecorder(fake, AgentSettings(), "conv-1")
    recorder._item_added(said("user", "hello"))
    recorder._item_added(said("assistant", "Hi", e2e=0.5))
    await recorder.finish()
    assert [m["text"] for m in fake.turns[-1]["messages"]] == ["hello", "Hi"]


def test_recorder_follows_the_callers_language():
    switches = []
    recorder = CallRecorder(FakeApi(), AgentSettings(), "conv-1", on_language=switches.append)
    for language, final in [("te-IN", True), ("te-IN", True), ("hi-IN", False), ("hi-IN", True)]:
        recorder._transcribed(SimpleNamespace(is_final=final, language=language))
    assert switches == ["te-IN", "hi-IN"] and recorder.language == "hi-IN"


def test_call_cost_adds_llm_speech_to_text_and_text_to_speech():
    recorder = CallRecorder(FakeApi(), AgentSettings(), "conv-1")
    recorder._usage_updated(
        SimpleNamespace(
            usage=AgentSessionUsage(
                model_usage=[
                    LLMModelUsage(
                        provider="google", model="m", input_tokens=1000, output_tokens=100
                    ),
                    STTModelUsage(provider="sarvam", model="saaras:v4", audio_duration=60.0),
                    TTSModelUsage(provider="sarvam", model="bulbul:v4-flash", characters_count=500),
                ]
            )
        )
    )
    s = AgentSettings()
    llm_inr = (
        (1000 * s.llm_input_usd_per_million + 100 * s.llm_output_usd_per_million)
        / 1e6
        * s.usd_to_inr
    )
    stt_inr = 60 / 3600 * 29.40  # one minute of caller audio
    tts_inr = 500 / 10_000 * 10.0  # 500 characters spoken
    assert recorder.cost_inr == pytest.approx(llm_inr + stt_inr + tts_inr, abs=1e-4)


@pytest.mark.parametrize(
    ("language", "expected"),
    [("te", "te-IN"), ("hi-IN", "hi-IN"), ("en", "en-IN"), ("fr", None), (None, None)],
)
def test_text_to_speech_language(language, expected):
    assert tts_language(language) == expected


async def test_voice_prompt_asks_for_native_script_and_spoken_greeting(client):
    context = (await client.get("/v1/agent/context")).json()
    prompt = build_system_prompt(context, channel="voice", verified_phone=None)
    assert "write Telugu in Telugu script and Hindi in Devanagari" in prompt
    assert "Greet the caller first" in prompt
    assert "Greet only once" in prompt
    assert "check availability right away" in prompt
    assert "Read it back digit by digit" in prompt
    assert "Romanised Telugu" not in prompt


def test_greeting_is_spoken_in_the_business_languages_own_script():
    assert voice_greeting_instructions({"languages": ["te", "en"]}) == (
        "Greet the caller now, in Telugu, written in Telugu script."
    )
    assert voice_greeting_instructions({"languages": ["hi"]}).endswith("written in Devanagari.")
    assert voice_greeting_instructions({"languages": ["en"]}) == "Greet the caller now, in English."


class SpokenSession:
    def __init__(self):
        self.spoken = []

    def say(self, text, **kwargs):
        self.spoken.append(text)


def test_one_moment_is_said_once_per_reply_in_the_callers_language():
    session = SpokenSession()
    phrases = StockPhrases(session, "te-IN")
    reply = SimpleNamespace(speech_handle=SimpleNamespace(id="speech_1"))
    phrases.one_moment(reply)
    phrases.one_moment(reply)  # a second tool in the same reply
    phrases.language = "hi-IN"  # the caller switched to Hindi
    phrases.one_moment(SimpleNamespace(speech_handle=SimpleNamespace(id="speech_2")))
    phrases.language = "ta-IN"  # no phrase for this language: stay quiet
    phrases.one_moment(SimpleNamespace(speech_handle=SimpleNamespace(id="speech_3")))
    assert session.spoken == [ONE_MOMENT["te-IN"], ONE_MOMENT["hi-IN"]]


def llm_error(recoverable: bool) -> ErrorEvent:
    error = llm.LLMError(
        timestamp=0, label="gemini", error=RuntimeError("503"), recoverable=recoverable
    )
    return ErrorEvent(error=error, source=None)


def test_caller_hears_an_apology_only_when_every_model_failed():
    session = SpokenSession()
    phrases = StockPhrases(session, "te-IN")
    phrases.on_error(llm_error(recoverable=True))  # being retried
    phrases.on_error(llm_error(recoverable=False))
    assert session.spoken == [SAY_AGAIN["te-IN"]]


def test_llm_deadline_stays_above_geminis_minimum():
    with pytest.raises(ValueError):
        AgentSettings(voice_llm_timeout_seconds=3)


def test_calls_fall_back_to_a_second_model():
    s = AgentSettings(gemini_api_key="test", voice_fallback_model="gemini-3.1-flash-lite")
    model = voice_llm(s)
    assert isinstance(model, llm.FallbackAdapter)
    assert [m.model for m in model._llm_instances] == [s.gemini_model, "gemini-3.1-flash-lite"]
    assert model._attempt_timeout == s.voice_llm_timeout_seconds
    # A tool call made by one model can be continued by the other.
    main, fallback = model._llm_instances
    main._thought_signatures["call_1"] = b"signature"
    assert fallback._thought_signatures == {"call_1": b"signature"}
    assert not isinstance(
        voice_llm(AgentSettings(gemini_api_key="t", voice_fallback_model="")), llm.FallbackAdapter
    )


def test_each_language_gets_its_own_voice():
    speakers = AgentSettings().sarvam_tts_speakers
    assert tts_voice("te", speakers) == ("te-IN", "pooja_te_conversation")
    assert tts_voice("hi-IN", speakers) == ("hi-IN", "ishita_enhi_customer")
    assert tts_voice("ta-IN", speakers) is None  # no voice configured: keep the current one


def test_configured_voices_are_valid_for_the_model():
    from livekit.plugins.sarvam.tts import validate_model_speaker_compatibility

    settings = AgentSettings()
    for speaker in settings.sarvam_tts_speakers.values():
        assert validate_model_speaker_compatibility(settings.sarvam_tts_model, speaker), speaker

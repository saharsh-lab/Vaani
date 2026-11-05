"""Real-time voice agent on LiveKit.

Silero VAD -> Sarvam speech-to-text (streaming) -> Gemini with the six tools ->
Sarvam Bulbul text-to-speech. LiveKit streams each stage into the next, so the
agent starts speaking before the whole reply is generated.

    python -m vaani_agent.voice download-files   # once: model files for the plugins
    python -m vaani_agent.voice dev               # register with LiveKit and take calls

The API dispatches a call here by creating a room whose token names this agent
and carries the business id (see app/api/voice.py).
"""

import asyncio
import dataclasses
import json
import logging
import statistics
import typing
from collections.abc import Callable
from typing import Any

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    APIConnectOptions,
    ErrorEvent,
    JobContext,
    JobProcess,
    RunContext,
    SessionConnectOptions,
    cli,
    function_tool,
    llm,
)
from livekit.agents.metrics import (
    AgentSessionUsage,
    LLMModelUsage,
    STTModelUsage,
    TTSModelUsage,
)
from livekit.plugins import google, sarvam, silero
from livekit.plugins.sarvam.tts import SarvamTTSLanguages

from vaani_agent.api_client import VaaniApi
from vaani_agent.config import VOICE_AGENT_NAME, AgentSettings, get_agent_settings
from vaani_agent.observability import init_sentry
from vaani_agent.prompt import build_system_prompt, voice_greeting_instructions
from vaani_agent.runtime import OUTCOMES
from vaani_agent.tools import TOOLS, ToolContext, prepare_args

log = logging.getLogger("vaani.voice")

TTS_LANGUAGES = set(typing.get_args(SarvamTTSLanguages))
# Said the moment Gemini decides to use a tool. Its answer needs a second Gemini call
# after the tool (one to three seconds), and silence that long on a call sounds like
# the line dropped. Languages without an entry stay silent.
ONE_MOMENT = {"te-IN": "ఒక్క నిమిషం.", "hi-IN": "एक मिनट.", "en-IN": "One moment."}
# Said when no model could answer (a Gemini outage), instead of going quiet.
SAY_AGAIN = {
    "te-IN": "క్షమించండి, మళ్ళీ ఒకసారి చెప్పగలరా?",
    "hi-IN": "माफ़ कीजिए, क्या आप एक बार फिर बता सकते हैं?",
    "en-IN": "Sorry, could you say that again?",
}
TIME_UP_INSTRUCTIONS = (
    "The call time limit has been reached. In one short sentence, apologise, say the team "
    "can call them back, and say goodbye."
)


def tts_language(language: str | None) -> str | None:
    """Business language (te) or detected language (te-IN) -> a Bulbul language code."""
    if not language:
        return None
    code = language if "-" in language else f"{language}-IN"
    return code if code in TTS_LANGUAGES else None


def tts_voice(language: str | None, speakers: dict[str, str]) -> tuple[str, str] | None:
    """(Bulbul language code, speaker) if we have a voice for this language."""
    code = tts_language(language)
    return (code, speakers[code]) if code in speakers else None


class SarvamSTT(sarvam.STT):
    """Sarvam streaming speech-to-text that finalises as soon as the caller stops.

    The plugin can send Sarvam a flush, but doesn't declare `manual_flush`, so LiveKit
    never asks it to; the transcript then waits for Sarvam's own silence timeout.
    Declaring it makes LiveKit flush when Silero VAD hears the end of speech.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(flush_signal=True, **kwargs)
        self._capabilities = dataclasses.replace(self._capabilities, manual_flush=True)


def _ms(seconds: float | None) -> str:
    return "?" if seconds is None else f"{seconds * 1000:.0f} ms"


class CallRecorder:
    """Saves the call as it happens: transcript lines and tool calls, outcome,
    detected language, per-reply latency and running cost."""

    def __init__(
        self,
        api: VaaniApi,
        settings: AgentSettings,
        conversation_id: str,
        on_language: Callable[[str], None] | None = None,
    ) -> None:
        self.api = api
        self.settings = settings
        self.conversation_id = conversation_id
        self.on_language = on_language
        self.pending: list[dict] = []
        self.outcomes: set[str] = set()
        self.latencies_ms: list[int] = []
        self.language: str | None = None
        self.usage: AgentSessionUsage | None = None
        self._saving = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    def attach(self, session: AgentSession) -> None:
        session.on("conversation_item_added", self._item_added)
        session.on("user_input_transcribed", self._transcribed)
        session.on("session_usage_updated", self._usage_updated)

    # Events -----------------------------------------------------------------

    def tool_called(self, name: str, args: dict, result: dict) -> None:
        if name in OUTCOMES and "error" not in result:
            self.outcomes.add(OUTCOMES[name])
        self.pending.append(
            {"role": "tool", "tool_name": name, "tool_args": args, "tool_result": result}
        )

    def _item_added(self, event) -> None:
        item = event.item
        if not isinstance(item, llm.ChatMessage) or item.role not in ("user", "assistant"):
            return
        text = item.text_content
        if not text:
            return
        entry: dict[str, Any] = {"role": item.role, "text": text}
        if item.role == "assistant":
            # Caller stops speaking -> first audio of the reply.
            metrics = item.metrics or {}
            e2e = metrics.get("e2e_latency")
            if e2e is not None:
                entry["latency_ms"] = int(e2e * 1000)
                self.latencies_ms.append(entry["latency_ms"])
                log.info(
                    "reply after %d ms (llm first token %s, tts first audio %s)",
                    entry["latency_ms"],
                    _ms(metrics.get("llm_node_ttft")),
                    _ms(metrics.get("tts_node_ttfb")),
                )
        self.pending.append(entry)
        if item.role == "assistant":
            task = asyncio.create_task(self.save())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    def _transcribed(self, event) -> None:
        if not event.is_final or not event.language:
            return
        language = str(event.language)
        if language != self.language:
            self.language = language
            if self.on_language:
                self.on_language(language)

    def _usage_updated(self, event) -> None:
        self.usage = event.usage

    # Totals -----------------------------------------------------------------

    def _totals(self) -> tuple[int, int, float, int]:
        tokens_in = tokens_out = chars = 0
        audio_s = 0.0
        for usage in self.usage.model_usage if self.usage else []:
            if isinstance(usage, LLMModelUsage):
                tokens_in += usage.input_tokens
                tokens_out += usage.output_tokens
            elif isinstance(usage, STTModelUsage):
                audio_s += usage.audio_duration
            elif isinstance(usage, TTSModelUsage):
                chars += usage.characters_count
        return tokens_in, tokens_out, audio_s, chars

    @property
    def cost_inr(self) -> float:
        s = self.settings
        tokens_in, tokens_out, audio_s, chars = self._totals()
        llm_usd = (
            tokens_in * s.llm_input_usd_per_million + tokens_out * s.llm_output_usd_per_million
        ) / 1_000_000
        return round(
            llm_usd * s.usd_to_inr
            + audio_s / 3600 * s.sarvam_stt_inr_per_hour
            + chars / 10_000 * s.sarvam_tts_inr_per_10k_chars,
            4,
        )

    @property
    def outcome(self) -> str:
        for outcome in OUTCOMES.values():
            if outcome in self.outcomes:
                return outcome
        return "info"

    # Persistence ------------------------------------------------------------

    async def save(self, force: bool = False) -> None:
        async with self._saving:
            messages, self.pending = self.pending, []
            if not messages and not force:
                return
            tokens_in, tokens_out, _, _ = self._totals()
            try:
                await self.api.save_turn(
                    self.conversation_id,
                    messages=messages,
                    outcome=self.outcome,
                    llm_input_tokens=tokens_in,
                    llm_output_tokens=tokens_out,
                    cost_inr=self.cost_inr,
                    language=self.language,
                )
            except Exception:
                log.exception("failed to save call turn; will retry")
                self.pending = messages + self.pending

    async def finish(self, reason: str = "") -> None:
        """Shutdown callback: flush everything, close the conversation, log a summary."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.save(force=True)
        try:
            await self.api.end_conversation(self.conversation_id, outcome=self.outcome)
        except Exception:
            log.exception("failed to end conversation %s", self.conversation_id)
        finally:
            await self.api.http.aclose()
        ordered = sorted(self.latencies_ms) or [0]
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        log.info(
            "call %s ended (%s): %d replies, latency p50 %d ms p95 %d ms, outcome %s, ₹%.4f",
            self.conversation_id,
            reason or "caller left",
            len(self.latencies_ms),
            statistics.median(ordered),
            p95,
            self.outcome,
            self.cost_inr,
        )


class StockPhrases:
    """Fixed lines spoken in the caller's current language, without asking Gemini."""

    def __init__(self, session: AgentSession, language: str) -> None:
        self.session = session
        self.language = language
        self._said_for: set[str] = set()

    def one_moment(self, context: RunContext) -> None:
        """Before a tool runs; once per reply, however many tools it calls."""
        reply = context.speech_handle.id
        text = ONE_MOMENT.get(self.language)
        if text and reply not in self._said_for:
            self._said_for.add(reply)
            # Not awaited: the tool runs while it plays, and the answer queues behind it.
            self.session.say(text, add_to_chat_ctx=False)

    def on_error(self, event: ErrorEvent) -> None:
        # Recoverable errors are retried; this one means every model failed.
        if isinstance(event.error, llm.LLMError) and not event.error.recoverable:
            log.warning("no model could answer: %s", event.error.error)
            self.session.say(
                SAY_AGAIN.get(self.language, SAY_AGAIN["en-IN"]), add_to_chat_ctx=False
            )


def voice_llm(s: AgentSettings) -> llm.LLM:
    """Gemini for calls: low thinking for speed, and a second model to fall back to
    when the first errors or stalls (on 5 Nov 2026, 3.5 Flash-Lite returned 503s and
    30 s replies while 3.1 Flash-Lite answered in about 1.3 s)."""
    extra: dict[str, Any] = {"temperature": 0.2}
    if s.voice_thinking_level:
        extra["thinking_config"] = {"thinking_level": s.voice_thinking_level}
    models = [s.gemini_model] + [m for m in [s.voice_fallback_model] if m and m != s.gemini_model]
    instances = [google.LLM(model=m, api_key=s.gemini_api_key, **extra) for m in models]
    if len(instances) == 1:
        return instances[0]
    # Gemini 3 sends back a signature with each tool call and refuses a history without
    # it (400 "missing a thought_signature"). The plugin keeps them per model, so after
    # a tool call the fallback failed exactly when it was needed. Each model accepts the
    # other's signatures, so they share one store.
    shared: dict[str, bytes] = {}
    for instance in instances:
        if not hasattr(instance, "_thought_signatures"):
            log.warning("livekit-plugins-google changed; fallback may lose tool-call signatures")
        instance._thought_signatures = shared
    return llm.FallbackAdapter(instances, attempt_timeout=s.voice_llm_timeout_seconds)


def livekit_tools(
    api: VaaniApi,
    tool_context: ToolContext,
    recorder: CallRecorder,
    before_tool: Callable[[RunContext], None] | None = None,
) -> list:
    """The six tools, declared with the same JSON schemas the text agent uses."""

    def make(spec: dict):
        name = spec["name"]

        # LiveKit passes the context by type; it's None when a test calls the tool directly.
        async def run(raw_arguments: dict[str, Any], context: RunContext = None) -> str:  # type: ignore[assignment]
            if before_tool and context is not None:
                before_tool(context)
            args = prepare_args(name, raw_arguments, tool_context)
            result = await api.call_tool(name, args)
            recorder.tool_called(name, args, result)
            return json.dumps(result, ensure_ascii=False)

        return function_tool(run, raw_schema=spec)

    return [make(spec) for spec in TOOLS]


class VaaniVoiceAgent(Agent):
    def __init__(self, context: dict, tools: list) -> None:
        super().__init__(
            instructions=build_system_prompt(context, channel="voice", verified_phone=None),
            tools=tools,
        )


def prewarm(proc: JobProcess) -> None:
    init_sentry("voice-worker")
    proc.userdata["vad"] = silero.VAD.load()


settings = get_agent_settings()
server = AgentServer(
    setup_fnc=prewarm,
    num_idle_processes=settings.voice_idle_processes,
    ws_url=settings.livekit_url,
    api_key=settings.livekit_api_key,
    api_secret=settings.livekit_api_secret,
)


@server.rtc_session(agent_name=VOICE_AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    s = get_agent_settings()
    business_id = json.loads(ctx.job.metadata or "{}").get("business_id")
    if not business_id:
        log.error("call dispatched without a business_id; leaving room %s", ctx.room.name)
        return

    api = VaaniApi(s.api_base_url, s.agent_api_key, business_id)
    context = await api.context()
    conversation = await api.start_conversation("voice")
    tool_context = ToolContext(conversation_id=conversation["id"], channel="voice")

    language, speaker = (
        tts_voice(context["languages"][0], s.sarvam_tts_speakers)
        or tts_voice("en-IN", s.sarvam_tts_speakers)
        or ("en-IN", None)  # None: the plugin's default voice for the model
    )
    tts = sarvam.TTS(
        target_language_code=language,
        model=s.sarvam_tts_model,
        speaker=speaker,
        enable_preprocessing=True,  # numbers, dates and mixed-language text read naturally
        api_key=s.sarvam_api_key,
    )

    def follow_language(detected: str) -> None:
        # Speak in whatever language the caller just used, in that language's voice.
        if voice := tts_voice(detected, s.sarvam_tts_speakers):
            tts.update_options(target_language_code=voice[0], speaker=voice[1])
            phrases.language = voice[0]

    recorder = CallRecorder(api, s, conversation["id"], on_language=follow_language)
    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=SarvamSTT(
            language="unknown",  # detect Telugu / Hindi / English per utterance
            model=s.sarvam_stt_model,
            mode=s.sarvam_stt_mode,
            api_key=s.sarvam_api_key,
        ),
        llm=voice_llm(s),
        tts=tts,
        turn_handling={"turn_detection": "vad"},
        conn_options=SessionConnectOptions(
            # LiveKit drops a speech-to-text socket that sends nothing back, not even a
            # pong, for 6 s. Sarvam was that slow at busy moments, and each drop lost what
            # the caller said while it reconnected.
            stt_conn_options=APIConnectOptions(liveness_timeout=s.voice_stt_liveness_seconds),
        ),
    )
    phrases = StockPhrases(session, language)
    session.on("error", phrases.on_error)
    recorder.attach(session)
    ctx.add_shutdown_callback(recorder.finish)

    await session.start(
        agent=VaaniVoiceAgent(
            context, livekit_tools(api, tool_context, recorder, phrases.one_moment)
        ),
        room=ctx.room,
    )
    session.generate_reply(instructions=voice_greeting_instructions(context))

    async def end_when_time_is_up() -> None:
        await asyncio.sleep(s.voice_max_call_seconds)
        handle = session.generate_reply(
            instructions=TIME_UP_INSTRUCTIONS, allow_interruptions=False
        )
        await handle.wait_for_playout()
        ctx.shutdown(reason="max call duration")

    timer = asyncio.create_task(end_when_time_is_up())

    async def stop_timer(_reason: str) -> None:  # shutdown callbacks must be coroutines
        timer.cancel()

    ctx.add_shutdown_callback(stop_timer)


if __name__ == "__main__":
    cli.run_app(server)

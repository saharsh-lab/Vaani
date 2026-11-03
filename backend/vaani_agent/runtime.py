"""The channel-independent agent loop: one Gemini model, a system prompt, six tools.

The CLI uses this now; the WhatsApp webhook and the LiveKit voice worker will
wrap the same AgentSession.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types

from vaani_agent.api_client import VaaniApi
from vaani_agent.config import AgentSettings
from vaani_agent.prompt import build_system_prompt
from vaani_agent.tools import TOOLS, ToolContext, prepare_args

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
FALLBACK_REPLY = "Sorry, I didn't catch that. Could you say it again?"

# Highest first: the conversation's outcome is the most significant thing that happened.
OUTCOMES = {
    "handoff_to_human": "handoff",
    "create_booking": "booked",
    "reschedule_or_cancel": "changed",
}


@dataclass(frozen=True)
class VoiceNote:
    """How a turn's text was produced, when it came from speech."""

    language_code: str | None  # as detected by speech-to-text, e.g. te-IN
    transcription_ms: int
    cost_inr: float


def gemini_tools() -> list[types.Tool]:
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters_json_schema=t["parameters"],
                )
                for t in TOOLS
            ]
        )
    ]


class AgentSession:
    def __init__(
        self,
        *,
        api: VaaniApi,
        llm: Any,  # genai.Client, or anything with .aio.models.generate_content
        settings: AgentSettings,
        context: dict,
        tool_context: ToolContext,
        persist_state: bool = False,  # save history each turn, for channels that resume later
    ) -> None:
        self.api = api
        self.llm = llm
        self.settings = settings
        self.tool_context = tool_context
        self.persist_state = persist_state
        self.system_prompt = build_system_prompt(
            context, channel=tool_context.channel, verified_phone=tool_context.verified_phone
        )
        self.config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=gemini_tools(),
            temperature=0.2,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        self.history: list[types.Content] = []
        self.input_tokens = 0
        self.output_tokens = 0
        self.latencies_ms: list[int] = []
        self.outcomes: set[str] = set()
        self.speech_cost_inr = 0.0  # speech-to-text, on top of the LLM cost
        self.language: str | None = None

    @classmethod
    def gemini_client(cls, settings: AgentSettings) -> genai.Client:
        return genai.Client(api_key=settings.gemini_api_key)

    def export_state(self) -> dict:
        """JSON-safe snapshot (binary thought signatures become base64)."""
        return {
            "history": [c.model_dump(mode="json", exclude_none=True) for c in self.history],
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "outcomes": sorted(self.outcomes),
            "speech_cost_inr": self.speech_cost_inr,
            "language": self.language,
        }

    def restore(self, state: dict) -> None:
        self.history = [types.Content.model_validate(c) for c in state.get("history", [])]
        self.input_tokens = state.get("input_tokens", 0)
        self.output_tokens = state.get("output_tokens", 0)
        self.outcomes = set(state.get("outcomes", []))
        self.speech_cost_inr = state.get("speech_cost_inr", 0.0)
        self.language = state.get("language")

    async def reply(self, user_text: str, voice: VoiceNote | None = None) -> str:
        started = time.perf_counter()
        user_entry: dict = {"role": "user", "text": user_text}
        if voice:
            # Tell the model the text came from speech, so it double-checks
            # names and numbers that the recogniser may have misheard.
            tag = f"voice note, {voice.language_code}" if voice.language_code else "voice note"
            user_text = f"[{tag}] {user_text}"
            user_entry = {"role": "user", "text": user_text, "latency_ms": voice.transcription_ms}
            self.speech_cost_inr += voice.cost_inr
            self.language = voice.language_code or self.language
        transcript: list[dict] = [user_entry]
        turn_start = len(self.history)
        self.history.append(
            types.Content(role="user", parts=[types.Part.from_text(text=user_text)])
        )
        try:
            text = await self._run_model(transcript)
        except Exception:
            # Drop the half-finished turn so the history stays user/model alternating.
            del self.history[turn_start:]
            raise

        latency_ms = int((time.perf_counter() - started) * 1000)
        self.latencies_ms.append(latency_ms)
        transcript.append({"role": "assistant", "text": text, "latency_ms": latency_ms})
        await self._save(transcript)
        return text

    async def _run_model(self, transcript: list[dict]) -> str:
        """Call the model, running tools it asks for, until it answers in text."""
        for _ in range(MAX_TOOL_ROUNDS):
            response = await self.llm.aio.models.generate_content(
                model=self.settings.gemini_model, contents=self.history, config=self.config
            )
            self._count_usage(response.usage_metadata)
            candidate = response.candidates[0] if response.candidates else None
            if candidate is None or candidate.content is None:
                break
            self.history.append(candidate.content)

            calls = response.function_calls or []
            if not calls:
                text = (response.text or "").strip()
                if text:
                    return text
                self.history.pop()  # an empty model turn; the fallback below replaces it
                break

            results = []
            for call in calls:
                args = prepare_args(call.name, dict(call.args or {}), self.tool_context)
                result = await self.api.call_tool(call.name, args)
                if call.name in OUTCOMES and "error" not in result:
                    self.outcomes.add(OUTCOMES[call.name])
                transcript.append(
                    {
                        "role": "tool",
                        "tool_name": call.name,
                        "tool_args": args,
                        "tool_result": result,
                    }
                )
                results.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call.id, name=call.name, response=result
                        )
                    )
                )
            self.history.append(types.Content(role="user", parts=results))

        # No usable answer (empty, blocked, or too many tool rounds): record what we
        # told the customer as the model's turn so the next turn starts cleanly.
        self.history.append(
            types.Content(role="model", parts=[types.Part.from_text(text=FALLBACK_REPLY)])
        )
        return FALLBACK_REPLY

    def _count_usage(self, usage: types.GenerateContentResponseUsageMetadata | None) -> None:
        if usage is None:
            return
        self.input_tokens += usage.prompt_token_count or 0
        # Thinking tokens are billed as output.
        self.output_tokens += (usage.candidates_token_count or 0) + (
            usage.thoughts_token_count or 0
        )

    @property
    def cost_inr(self) -> float:
        """LLM plus speech-to-text cost so far."""
        s = self.settings
        usd = (
            self.input_tokens * s.llm_input_usd_per_million
            + self.output_tokens * s.llm_output_usd_per_million
        ) / 1_000_000
        return round(usd * s.usd_to_inr + self.speech_cost_inr, 4)

    @property
    def outcome(self) -> str:
        for outcome in OUTCOMES.values():
            if outcome in self.outcomes:
                return outcome
        return "info"

    async def _save(self, transcript: list[dict]) -> None:
        try:
            await self.api.save_turn(
                self.tool_context.conversation_id,
                messages=transcript,
                outcome=self.outcome,
                llm_input_tokens=self.input_tokens,
                llm_output_tokens=self.output_tokens,
                cost_inr=self.cost_inr,
                language=self.language,
                agent_state=self.export_state() if self.persist_state else None,
            )
        except Exception:  # saving must never break the conversation
            log.exception("failed to save turn")

    async def end(self) -> None:
        await self.api.end_conversation(self.tool_context.conversation_id, outcome=self.outcome)

"""Stand-ins for Gemini: canned responses, real google-genai types."""

from types import SimpleNamespace

from google.genai import types

USAGE = types.GenerateContentResponseUsageMetadata(
    prompt_token_count=1000, candidates_token_count=20
)


def model_says(text: str) -> types.GenerateContentResponse:
    return _response(types.Part.from_text(text=text))


def model_calls(name: str, **args) -> types.GenerateContentResponse:
    return _response(types.Part(function_call=types.FunctionCall(name=name, args=args)))


def _response(part: types.Part) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))],
        usage_metadata=USAGE,
    )


class ScriptedModel:
    """Returns canned responses in order and records what it was sent."""

    def __init__(self, responses: list[types.GenerateContentResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[list[types.Content]] = []
        self.aio = SimpleNamespace(models=self)

    async def generate_content(self, *, model, contents, config):
        self.requests.append(list(contents))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def ogg_opus(seconds: float, pre_skip: int = 312) -> bytes:
    """A structurally valid Ogg Opus file (headers, page layout, granule positions)
    of the given length. The audio packets are filler, so it won't decode, but the
    length can be read from it exactly as from a real WhatsApp voice note."""
    import struct

    def page(granule: int, seq: int, payload: bytes, header_type: int = 0) -> bytes:
        segments = [255] * (len(payload) // 255) + [len(payload) % 255]
        return (
            b"OggS"
            + struct.pack("<BBqIIIB", 0, header_type, granule, 0x5A5A, seq, 0, len(segments))
            + bytes(segments)
            + payload
        )

    head = b"OpusHead" + struct.pack("<BBHIhB", 1, 1, pre_skip, 16_000, 0, 0)
    tags = b"OpusTags" + struct.pack("<I", 5) + b"vaani" + struct.pack("<I", 0)
    total = int(seconds * 48_000) + pre_skip
    pages = [page(0, 0, head, header_type=2), page(0, 1, tags)]
    pages += [page(total // 2, 2, b"\x00" * 300), page(total, 3, b"\x00" * 300, header_type=4)]
    return b"".join(pages)


class ScriptedLiveKitLLM:
    """For LiveKit's AgentSession: each step is reply text or (tool_name, args)."""

    def __new__(cls, steps):
        import json as _json

        from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, llm

        class _Stream(llm.LLMStream):
            def __init__(self, owner, step, **kwargs):
                super().__init__(owner, **kwargs)
                self.step = step

            async def _run(self):
                if isinstance(self.step, str):
                    delta = llm.ChoiceDelta(role="assistant", content=self.step)
                else:
                    name, args = self.step
                    call = llm.FunctionToolCall(
                        name=name, arguments=_json.dumps(args), call_id=f"call_{name}"
                    )
                    delta = llm.ChoiceDelta(role="assistant", tool_calls=[call])
                usage = llm.CompletionUsage(
                    completion_tokens=20, prompt_tokens=1000, total_tokens=1020
                )
                self._event_ch.send_nowait(llm.ChatChunk(id="chunk", delta=delta, usage=usage))

        class _LLM(llm.LLM):
            def __init__(self):
                super().__init__()
                self.steps = list(steps)
                self.requests = []

            def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **_):
                self.requests.append(chat_ctx.copy())
                return _Stream(
                    self,
                    self.steps.pop(0),
                    chat_ctx=chat_ctx,
                    tools=tools or [],
                    conn_options=conn_options,
                )

        return _LLM()

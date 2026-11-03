"""LLM-as-judge: rubric checks (FAQ answers, language, refusals) and hallucination.

One judge call per conversation. The judge sees the clinic's facts (the system
prompt and the FAQ documents), the transcript including every tool result, and
lists any reply claim those don't support.
"""

import json

from google.genai import types

from app.seed import FAQS
from evals.harness import ConversationResult

SCHEMA = {
    "type": "object",
    "properties": {
        "rubric_pass": {"type": "boolean"},
        "rubric_reason": {"type": "string"},
        "replies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "unsupported_claims": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["index", "unsupported_claims"],
            },
        },
    },
    "required": ["rubric_pass", "rubric_reason", "replies"],
}

INSTRUCTIONS = """You grade an AI receptionist for a dental clinic in India. You will get
the clinic's facts, a conversation (with every tool result the receptionist saw), and
a rubric.

1. Rubric: decide whether the conversation satisfies the rubric. If there is no
   rubric, set rubric_pass to true.
2. Hallucination: for each receptionist reply, list specific factual claims that are
   NOT supported by the clinic facts or by a tool result shown before that reply.
   Claims are things like prices, times, available slots, dates, policies, staff,
   services, addresses or booking outcomes. Greetings, questions, offers to help,
   restating what the customer said, and saying "I don't know" are not claims.
   Translating a supported fact into Telugu or Hindi is still supported.
   Use an empty list when every claim is supported.

Return JSON only."""


def transcript(result: ConversationResult) -> str:
    lines = []
    reply_index = 0
    for turn in result.turns:
        lines.append(f"Customer: {turn.user}")
        for tool in turn.tools:
            lines.append(
                f"  [tool {tool['name']}({json.dumps(tool['args'], ensure_ascii=False)}) -> "
                f"{json.dumps(tool['result'], ensure_ascii=False)}]"
            )
        lines.append(f"Receptionist (reply {reply_index}): {turn.reply}")
        reply_index += 1
    return "\n".join(lines)


def facts(result: ConversationResult) -> str:
    faqs = "\n".join(f"- {title}: {content}" for title, content in FAQS)
    return f"{result.system_prompt}\n\nKnowledge base:\n{faqs}"


class Judge:
    def __init__(self, llm, model: str) -> None:
        self.llm = llm
        self.model = model

    async def grade(self, result: ConversationResult) -> None:
        """Fills in result.rubric and result.unsupported_claims."""
        rubric = result.scenario.expect.judge
        prompt = (
            f"<clinic_facts>\n{facts(result)}\n</clinic_facts>\n\n"
            f"<conversation>\n{transcript(result)}\n</conversation>\n\n"
            f"<rubric>\n{rubric or '(none)'}\n</rubric>"
        )
        try:
            response = await self.llm.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=INSTRUCTIONS,
                    temperature=0,
                    response_mime_type="application/json",
                    response_json_schema=SCHEMA,
                ),
            )
            verdict = json.loads(response.text)
        except Exception as exc:  # one failed judgement shouldn't sink the run
            if rubric:
                result.rubric = {
                    "pass": False,
                    "reason": f"judge error: {type(exc).__name__}: {exc}",
                }
            return
        claims = {r["index"]: r.get("unsupported_claims", []) for r in verdict.get("replies", [])}
        result.unsupported_claims = [claims.get(i, []) for i in range(len(result.turns))]
        if rubric:
            result.rubric = {
                "pass": bool(verdict.get("rubric_pass")),
                "reason": verdict.get("rubric_reason", ""),
            }

"""Turns eval results into the metrics table from the project spec."""

import statistics
from collections import defaultdict
from dataclasses import dataclass

from evals.dataset import BOOKING_CATEGORIES
from evals.harness import ConversationResult, UtteranceResult


@dataclass
class Metric:
    name: str
    value: float | None  # None: not measured in this run
    target: str
    meets: bool | None
    detail: str
    unit: str = "%"

    def shown(self) -> str:
        if self.value is None:
            return "–"
        if self.unit == "%":
            return f"{self.value:.0%}" if self.value in (0, 1) else f"{self.value:.1%}"
        if self.unit == "ms":
            return f"{self.value:,.0f} ms"
        return f"₹{self.value:.4f}"


def _rate(passed: int, total: int) -> float | None:
    return passed / total if total else None


def _percentile(values: list[int], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def metrics(
    conversations: list[ConversationResult],
    utterances: list[UtteranceResult],
    *,
    booking_target: float = 0.90,
) -> list[Metric]:
    # Items cut short by Gemini quota or overload say nothing about the agent.
    conversations = [r for r in conversations if not r.not_scored]
    utterances = [u for u in utterances if not u.not_scored]
    booking = [r for r in conversations if r.scenario.category in BOOKING_CATEGORIES]
    faq = [r for r in conversations if r.scenario.category == "faq" and r.rubric is not None]
    judged = [r for r in conversations if r.unsupported_claims]
    replies = [claims for r in judged for claims in r.unsupported_claims]
    with_claims = sum(1 for claims in replies if claims)
    latencies = [t.latency_ms for r in conversations for t in r.turns]
    handoffs = sum(r.handoff for r in conversations)
    expected_handoffs = sum(1 for r in conversations if r.scenario.expect.handoff)

    booking_rate = _rate(sum(r.passed for r in booking), len(booking))
    tool_rate = _rate(sum(u.passed for u in utterances), len(utterances))
    faq_rate = _rate(sum(r.passed for r in faq), len(faq))
    hallucination = _rate(with_claims, len(replies))
    p50, p95 = _percentile(latencies, 0.5), _percentile(latencies, 0.95)
    cost = statistics.mean(r.cost_inr for r in conversations) if conversations else None

    def meets(value, ok) -> bool | None:
        return None if value is None else ok(value)

    return [
        Metric(
            "Booking success rate",
            booking_rate,
            f"≥ {booking_target:.0%}",
            meets(booking_rate, lambda v: v >= booking_target),
            f"{sum(r.passed for r in booking)}/{len(booking)} booking, reschedule and cancel conversations",
        ),
        Metric(
            "Tool-call accuracy",
            tool_rate,
            "≥ 95%",
            meets(tool_rate, lambda v: v >= 0.95),
            f"{sum(u.passed for u in utterances)}/{len(utterances)} labelled utterances",
        ),
        Metric(
            "FAQ answer accuracy",
            faq_rate,
            "≥ 90%",
            meets(faq_rate, lambda v: v >= 0.90),
            f"{sum(r.passed for r in faq)}/{len(faq)} FAQ conversations (LLM judge)",
        ),
        Metric(
            "Hallucination rate",
            hallucination,
            "< 2%",
            meets(hallucination, lambda v: v < 0.02),
            f"{with_claims}/{len(replies)} replies with an unsupported claim (LLM judge)",
        ),
        Metric(
            "Handoff rate",
            _rate(handoffs, len(conversations)),
            "track",
            None,
            f"{handoffs} handoffs in {len(conversations)} conversations; {expected_handoffs} expected",
        ),
        Metric(
            "Agent turn latency p50",
            p50,
            "track",
            None,
            "text turns, model + tools, excluding rate-limit waits; voice latency comes from live calls",
            unit="ms",
        ),
        Metric("Agent turn latency p95", p95, "track", None, "", unit="ms"),
        Metric(
            "LLM cost per conversation",
            cost,
            "track",
            None,
            "Gemini tokens only; voice adds speech-to-text and voice costs",
            unit="inr",
        ),
    ]


def render(
    conversations: list[ConversationResult],
    utterances: list[UtteranceResult],
    rows: list[Metric],
    *,
    model: str,
    when: str,
) -> str:
    skipped = sum(r.not_scored for r in conversations) + sum(u.not_scored for u in utterances)
    out = [
        "# Vaani eval report",
        "",
        f"{when} · model `{model}` · {len(conversations)} conversations · "
        f"{len(utterances)} labelled utterances",
        "",
    ]
    if skipped:
        out += [
            f"**{skipped} not scored**: Gemini quota or overload errors (see the end). "
            "They're left out of every rate below; re-run when the quota resets.",
            "",
        ]
    out += [
        "| Metric | Result | Target | | Detail |",
        "| --- | --- | --- | --- | --- |",
    ]
    for m in rows:
        mark = {True: "✅", False: "❌", None: ""}[m.meets]
        out.append(f"| {m.name} | {m.shown()} | {m.target} | {mark} | {m.detail} |")
    out.append(
        "| Language detection accuracy | – | ≥ 95% | | needs recorded audio clips "
        "(Telugu, Hindi, English, mixed); not part of the text evals |"
    )

    if conversations:
        out += ["", "## Conversations by category", "", "| Category | Passed |", "| --- | --- |"]
        by_category = defaultdict(list)
        for r in conversations:
            by_category[r.scenario.category].append(r.passed)
        for category, passed in by_category.items():
            out.append(f"| {category} | {sum(passed)}/{len(passed)} |")

    if utterances:
        out += ["", "## Tool calls by language", "", "| Language | Correct |", "| --- | --- |"]
        by_lang = defaultdict(list)
        for u in utterances:
            by_lang[u.utterance.lang].append(u.passed)
        for lang, passed in sorted(by_lang.items()):
            out.append(f"| {lang} | {sum(passed)}/{len(passed)} |")

    failed = [r for r in conversations if not r.passed and not r.not_scored]
    if failed:
        out += ["", "## Failed conversations", ""]
        for r in failed:
            reasons = list(r.failures)
            if r.error:
                reasons.append(f"error: {r.error}")
            if r.rubric and not r.rubric["pass"]:
                reasons.append(f"judge: {r.rubric['reason']}")
            out.append(f"- **{r.scenario.id}**: " + "; ".join(reasons))

    claims = [
        (r.scenario.id, i, c)
        for r in conversations
        for i, cs in enumerate(r.unsupported_claims)
        for c in cs
    ]
    if claims:
        out += ["", "## Unsupported claims", ""]
        out += [f"- **{sid}** reply {i}: {c}" for sid, i, c in claims]

    wrong = [u for u in utterances if not u.passed and not u.not_scored]
    if wrong:
        out += ["", "## Wrong tool calls", ""]
        for u in wrong:
            why = u.error or "; ".join(u.mismatches)
            out.append(f"- **{u.utterance.id}** ({u.utterance.lang}) “{u.utterance.text}”: {why}")
    not_scored = [r.scenario.id for r in conversations if r.not_scored]
    not_scored += [u.utterance.id for u in utterances if u.not_scored]
    if not_scored:
        out += ["", "## Not scored (Gemini quota or overload)", "", ", ".join(not_scored)]
    return "\n".join(out) + "\n"


def to_json(
    conversations: list[ConversationResult], utterances: list[UtteranceResult], rows
) -> dict:
    return {
        "metrics": [
            {"name": m.name, "value": m.value, "target": m.target, "meets": m.meets} for m in rows
        ],
        "conversations": [
            {
                "id": r.scenario.id,
                "category": r.scenario.category,
                "passed": r.passed,
                "failures": r.failures,
                "error": r.error,
                "rubric": r.rubric,
                "handoff": r.handoff,
                "cost_inr": r.cost_inr,
                "unsupported_claims": r.unsupported_claims,
                "turns": [
                    {"user": t.user, "reply": t.reply, "tools": t.tools, "latency_ms": t.latency_ms}
                    for t in r.turns
                ],
            }
            for r in conversations
        ],
        "utterances": [
            {
                "id": u.utterance.id,
                "lang": u.utterance.lang,
                "passed": u.passed,
                "expected": u.utterance.tool,
                "got": u.first_tool,
                "args": u.args,
                "mismatches": u.mismatches,
                "error": u.error,
            }
            for u in utterances
        ],
    }

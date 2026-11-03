"""The eval suite itself: the datasets are consistent with the real booking engine,
and the harness scores right and wrong agent behaviour correctly (with a
scripted model in place of Gemini, so no API key is needed)."""

import asyncio
import json
from collections import Counter
from types import SimpleNamespace

import pytest
from google.genai import errors

from app.seed import SERVICES
from app.services.availability import parse_preference
from evals.dataset import NOW, load_scenarios, load_utterances, local
from evals.harness import (
    ConversationResult,
    RecordingApi,
    TurnRecord,
    UtteranceResult,
    _apply_setup,
    check,
    match_args,
    new_tenant,
    run_conversation,
    score_utterance,
)
from evals.judge import Judge
from evals.llm import ThrottledLLM
from evals.report import metrics, render
from tests.conftest import NOW as TEST_NOW
from tests.fakes import ScriptedModel, model_calls, model_says
from vaani_agent.config import AgentSettings

SCENARIOS = {s.id: s for s in load_scenarios()}
UTTERANCES = load_utterances()
SERVICE_NAMES = {name for name, *_ in SERVICES}


# The datasets ------------------------------------------------------------------


def test_dataset_sizes_match_the_spec():
    assert len(SCENARIOS) == 50
    assert Counter(s.category for s in SCENARIOS.values()) == {
        "booking": 15,
        "reschedule": 6,
        "cancel": 6,
        "faq": 10,
        "off_topic": 4,
        "angry": 4,
        "language_switch": 5,
    }
    assert len(UTTERANCES) == 100
    assert NOW == TEST_NOW  # evals and tests agree on "now"


@pytest.mark.parametrize("utterance", UTTERANCES, ids=lambda u: u.id)
def test_utterance_labels_are_valid(utterance):
    args = utterance.args
    if "service" in args:
        assert args["service"] in SERVICE_NAMES
    if "date" in args:
        assert local(f"{args['date']} 00:00") >= NOW.replace(hour=0)
    if "preferred_time" in args:
        parse_preference(args["preferred_time"])


@pytest.mark.parametrize("scenario", SCENARIOS.values(), ids=lambda s: s.id)
async def test_scenario_expectations_are_achievable(scenario, clean_db, client):
    """Setup bookings can be made, and every slot a scenario expects is actually
    free in the seeded schedule, so a failure always means the agent got it wrong."""
    business_id = await new_tenant(scenario.id)
    async with RecordingApi(str(business_id)) as api:
        await _apply_setup(api, scenario)
        targets = []
        if scenario.expect.booking:
            b = scenario.expect.booking
            targets.append((b.service, b.start, b.staff))
        if scenario.expect.rescheduled:
            service = next(
                s.service for s in scenario.setup if s.start == scenario.expect.rescheduled.from_
            )
            targets.append((service, scenario.expect.rescheduled.to, None))
        for service, start, staff in targets:
            assert service in SERVICE_NAMES
            when = local(start)
            body = {
                "service": service,
                "date": f"{when:%Y-%m-%d}",
                "preferred_time": f"{when:%H:%M}",
            }
            if staff:
                body["staff"] = staff
            result = await api.call_tool("check_availability", body)
            free = [s["start_at"] for s in result["slots"]]
            assert when.isoformat() in free, f"{scenario.id}: {start} isn't free ({free})"
        for start in [*scenario.expect.cancelled, *scenario.expect.unchanged]:
            assert any(s.start == start and s.mine for s in scenario.setup)


# Conversation scoring ------------------------------------------------------------


async def run_scripted(scenario_id: str, responses) -> ConversationResult:
    return await run_conversation(
        SCENARIOS[scenario_id], 0, llm=ScriptedModel(responses), settings=AgentSettings()
    )


RCT_STEPS = [
    model_calls(
        "check_availability",
        service="RCT consultation",
        date="2026-11-03",
        preferred_time="evening",
    ),
    model_says("Repu 5, 5:30 leda 6 ki undi."),
    model_says("Ravi garu, repu sayantram 6 ki RCT consultation. Confirm cheyana?"),
]


async def test_correct_booking_passes(clean_db):
    result = await run_scripted(
        "book-rct-tomorrow-evening-te",
        [
            *RCT_STEPS,
            model_calls(
                "create_booking",
                service="RCT consultation",
                start_at="2026-11-03T18:00:00",
                customer_name="Ravi",
                phone="9876543210",
            ),
            model_says("Booked."),
        ],
    )
    assert result.passed, result.failures
    assert [len(t.tools) for t in result.turns] == [1, 0, 1]
    assert result.cost_inr > 0


async def test_booking_at_the_wrong_time_fails_with_a_reason(clean_db):
    result = await run_scripted(
        "book-rct-tomorrow-evening-te",
        [
            *RCT_STEPS,
            model_calls(
                "create_booking",
                service="RCT consultation",
                start_at="2026-11-03T18:30:00",
                customer_name="Ravi",
                phone="9876543210",
            ),
            model_says("Booked."),
        ],
    )
    assert not result.passed
    assert result.failures == [
        "expected RCT consultation at 2026-11-03 18:00; got RCT consultation Tue 03 Nov 18:30 (confirmed)"
    ]


async def test_cancelling_the_wrong_booking_fails(clean_db):
    # Cancel the Tuesday booking although the customer asked for Friday.
    scenario = SCENARIOS["cancel-picks-the-right-booking-en"]
    business_id = await new_tenant("wrong-cancel")
    async with RecordingApi(str(business_id)) as api:
        setup = await _apply_setup(api, scenario)
    tuesday = setup["2026-11-03 17:00"]
    async with RecordingApi(str(business_id)) as api:
        await api.call_tool("reschedule_or_cancel", {"booking_id": tuesday, "action": "cancel"})
        conversation = await api.start_conversation("whatsapp", customer_phone=scenario.phone)
        failures = await check(scenario, business_id, conversation["id"], setup, api.tool_log)
    assert (
        "expected booking at 2026-11-06 11:00 cancelled; it's Teeth cleaning Fri 06 Nov 11:00 (confirmed)"
        in failures
    )
    assert any("2026-11-03 17:00 should be untouched" in f for f in failures)
    assert "never called find_booking" not in failures  # not required in this scenario


async def test_missing_handoff_and_unprompted_booking_fail(clean_db):
    result = await run_scripted(
        "angry-waiting-wants-owner-en", [model_says("Sorry for the wait! Anything else?")]
    )
    assert result.failures == ["expected a handoff"]

    result = await run_scripted(
        "angry-waiting-wants-owner-en",
        [
            model_calls("handoff_to_human", reason="angry", summary="Waiting 40 minutes"),
            model_says("I've asked the team to call you right away."),
        ],
    )
    assert result.passed and result.handoff


async def test_crash_is_a_failed_scenario_not_a_failed_run(clean_db):
    result = await run_scripted("faq-parking-en", [RuntimeError("Gemini down")])
    assert not result.passed and "Gemini down" in result.error


# Tool-call scoring ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("want", "got", "ok"),
    [
        ("evening", "evening", True),
        ("evening", "18:30", True),
        ("evening", "11:00", False),
        ("18:30", "6:30 pm", True),
        ("18:30", "06:30", False),
        ("18:30", None, False),
        ("morning", "garbage", False),
    ],
)
def test_preferred_time_matching(want, got, ok):
    assert (
        match_args("check_availability", {"preferred_time": want}, {"preferred_time": got}) == []
    ) is ok


def test_service_and_staff_matching():
    expected = {"service": "RCT consultation", "staff": "Arjun"}
    assert (
        match_args("x", expected, {"service": "rct consultation", "staff": "Dr. Arjun Rao"}) == []
    )
    assert match_args("x", expected, {"service": "General consultation", "staff": "Dr. Arjun Rao"})


def utterance(uid: str):
    return next(u for u in UTTERANCES if u.id == uid)


def test_utterance_scoring():
    ca01 = utterance("ca01")
    good = [
        {
            "name": "check_availability",
            "args": {
                "service": "RCT consultation",
                "date": "2026-11-03",
                "preferred_time": "evening",
            },
        }
    ]
    assert score_utterance(ca01, good, "").passed
    wrong_day = [{"name": "check_availability", "args": {**good[0]["args"], "date": "2026-11-04"}}]
    assert score_utterance(ca01, wrong_day, "").mismatches == [
        "date: expected '2026-11-03', got '2026-11-04'"
    ]
    assert not score_utterance(ca01, [], "Sure!").passed

    no06 = utterance("no06")  # price question: answering directly or searching are both fine
    assert score_utterance(no06, [], "₹1200").passed
    assert score_utterance(
        no06, [{"name": "search_knowledge", "args": {"question": "cleaning price"}}], ""
    ).passed
    assert not score_utterance(no06, [{"name": "handoff_to_human", "args": {}}], "").passed

    sk01 = utterance("sk01")
    assert score_utterance(
        sk01, [{"name": "search_knowledge", "args": {"question": "Is there parking?"}}], ""
    ).passed
    assert not score_utterance(
        sk01, [{"name": "search_knowledge", "args": {"question": "location"}}], ""
    ).passed


# Judge and report ---------------------------------------------------------------


class FakeJudgeModel:
    def __init__(self, verdict: dict):
        self.verdict = verdict
        self.aio = SimpleNamespace(models=self)
        self.prompts = []

    async def generate_content(self, *, model, contents, config):
        self.prompts.append(contents)
        return SimpleNamespace(text=json.dumps(self.verdict))


async def test_judge_fills_rubric_and_hallucinations():
    result = ConversationResult(SCENARIOS["faq-parking-en"], system_prompt="facts")
    result.turns = [TurnRecord("Is there parking?", "Yes, free valet parking.", [], 900)]
    model = FakeJudgeModel(
        {
            "rubric_pass": False,
            "rubric_reason": "invented valet parking",
            "replies": [{"index": 0, "unsupported_claims": ["free valet parking"]}],
        }
    )
    await Judge(model, "judge").grade(result)
    assert result.rubric == {"pass": False, "reason": "invented valet parking"}
    assert result.unsupported_claims == [["free valet parking"]]
    assert not result.passed
    assert "two-wheeler parking in front" in model.prompts[0]  # FAQ facts are in the prompt


def test_report_metrics_and_gate():
    def conv(sid, passed=True, claims=None):
        r = ConversationResult(SCENARIOS[sid], cost_inr=0.01)
        r.turns = [TurnRecord("u", "r", [], 1000)]
        r.failures = [] if passed else ["nope"]
        r.unsupported_claims = [claims or []]
        return r

    conversations = [
        conv("book-rct-tomorrow-evening-te"),
        conv("cancel-te", passed=False),
        conv("faq-parking-en", claims=["valet"]),
    ]
    conversations[2].rubric = {"pass": True, "reason": ""}
    utterances = [UtteranceResult(UTTERANCES[0], True, "check_availability", {}, [])]
    rows = {m.name: m for m in metrics(conversations, utterances)}
    assert rows["Booking success rate"].value == 0.5 and rows["Booking success rate"].meets is False
    assert rows["Tool-call accuracy"].value == 1.0
    assert rows["FAQ answer accuracy"].value == 1.0
    assert rows["Hallucination rate"].value == pytest.approx(1 / 3)
    markdown = render(conversations, utterances, list(rows.values()), model="m", when="now")
    assert "| Booking success rate | 50.0% | ≥ 90% | ❌ |" in markdown
    assert "**cancel-te**: nope" in markdown and "valet" in markdown


async def test_throttled_llm_retries_rate_limits(monkeypatch):
    calls = []

    class Flaky:
        aio = SimpleNamespace(models=None)

        async def generate_content(self, **kwargs):
            calls.append(kwargs)
            if len(calls) < 3:
                raise errors.ClientError(
                    429, {"error": {"message": "slow down", "status": "RESOURCE_EXHAUSTED"}}
                )
            return "ok"

    flaky = Flaky()
    flaky.aio.models = flaky

    async def no_sleep(_):
        return None

    monkeypatch.setattr("evals.llm.asyncio.sleep", no_sleep)
    llm = ThrottledLLM(flaky, rpm=6000, concurrency=2)
    assert await llm.aio.models.generate_content(model="m", contents="x") == "ok"
    assert len(calls) == 3


# Live-call stats -------------------------------------------------------------------


async def test_call_stats_from_saved_conversations(client, clinic, monkeypatch):
    from datetime import timedelta

    from app import clock
    from app.db import system_session
    from evals.calls import call_stats
    from evals.calls import render as render_calls

    async def voice_call(latencies, cost, minutes, language):
        conv = (await client.post("/v1/conversations", json={"channel": "voice"})).json()
        turn = {
            "messages": [{"role": "assistant", "text": "hi", "latency_ms": ms} for ms in latencies],
            "llm_input_tokens": 0,
            "llm_output_tokens": 0,
            "cost_inr": cost,
            "language": language,
        }
        await client.post(f"/v1/conversations/{conv['id']}/turns", json=turn)
        monkeypatch.setattr(clock, "now", lambda: TEST_NOW + timedelta(minutes=minutes))
        await client.post(f"/v1/conversations/{conv['id']}/end", json={})
        monkeypatch.setattr(clock, "now", lambda: TEST_NOW)

    await voice_call([800, 900, 1000], cost=4.0, minutes=2, language="te-IN")
    await voice_call([1200, 1500], cost=2.0, minutes=1, language="hi-IN")

    async with system_session() as session:
        stats = await call_stats(session, slug="sri-dental", channel="voice")
    (voice,) = stats["channels"]
    assert voice["conversations"] == 2 and voice["ended"] == 2
    assert voice["p50_ms"] == 1000 and voice["p95_ms"] == 1440  # interpolated, like Postgres
    assert voice["cost_per_minute_inr"] == pytest.approx(6.0 / 3)  # ₹6 over 3 minutes
    assert stats["languages"] == {"te-IN": 1, "hi-IN": 1}
    assert "| voice | 2 | 1,000 / 1,440 ms | ₹2.00 | 0% |" in render_calls(stats)


async def test_rate_limit_waits_are_not_counted_as_latency(monkeypatch):
    from evals.llm import WAITED

    class Limited:
        def __init__(self):
            self.calls = 0
            self.aio = SimpleNamespace(models=self)

        async def generate_content(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise errors.ClientError(429, {"error": {"message": "slow down"}})
            return "ok"

    real_sleep = asyncio.sleep

    async def short_sleep(seconds):
        await real_sleep(min(seconds, 0.05))  # backoff still takes measurable time

    monkeypatch.setattr("evals.llm.asyncio.sleep", short_sleep)
    llm = ThrottledLLM(Limited(), rpm=6000, concurrency=1)
    waited = [0.0]
    token = WAITED.set(waited)
    try:
        assert await llm.aio.models.generate_content(model="m", contents="x") == "ok"
    finally:
        WAITED.reset(token)
    assert waited[0] >= 0.04  # the backoff was recorded as waiting, not model time


async def test_quota_errors_are_not_scored_against_the_agent(clean_db):
    quota = errors.ClientError(429, {"error": {"message": "quota exceeded"}})
    result = await run_scripted("faq-parking-en", [quota])
    assert result.not_scored and not result.passed

    crashed = await run_scripted("faq-parking-en", [RuntimeError("bug")])
    assert not crashed.not_scored  # a real crash still counts as a failure

    good = ConversationResult(SCENARIOS["book-rct-tomorrow-evening-te"])
    rows = {m.name: m for m in metrics([good, crashed, result], [])}
    assert rows["Booking success rate"].value == 1.0  # 1/1: the quota-hit FAQ is excluded
    markdown = render([good, crashed, result], [], list(rows.values()), model="m", when="now")
    assert "**1 not scored**" in markdown and "faq-parking-en" in markdown.split("Not scored")[-1]

"""Run the eval suite against Gemini.

    python -m evals                      # everything: 50 conversations + 100 utterances
    python -m evals --only booking faq   # some conversation categories
    python -m evals --skip-utterances --limit 10
    python -m evals --skip-judge         # no LLM judge (FAQ and hallucination not scored)

Needs GEMINI_API_KEY and the database container. Uses its own database
(vaani_eval), recreated each run. Writes evals/reports/latest.md and .json, and
exits 1 if booking success falls below --fail-under (default 90%).
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

REPORTS = Path(__file__).parent / "reports"


def configure_environment(pg: str) -> None:
    """Point the app at the eval database. Must run before app modules read settings."""
    os.environ["DATABASE_URL"] = f"postgresql+psycopg://vaani_app:vaani_app@{pg}/vaani_eval"
    os.environ["ADMIN_DATABASE_URL"] = (
        f"postgresql+psycopg://vaani_admin:vaani_admin@{pg}/vaani_eval"
    )
    os.environ["AGENT_API_KEY"] = "eval-key"


def prepare_database(pg: str) -> None:
    import psycopg
    from alembic import command
    from alembic.config import Config

    with psycopg.connect(
        f"postgresql://vaani_admin:vaani_admin@{pg}/postgres", autocommit=True
    ) as c:
        c.execute("DROP DATABASE IF EXISTS vaani_eval WITH (FORCE)")
        c.execute("CREATE DATABASE vaani_eval")
        c.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vaani_app') THEN "
            "CREATE ROLE vaani_app LOGIN PASSWORD 'vaani_app'; END IF; END $$"
        )
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    config.set_main_option("sqlalchemy.url", os.environ["ADMIN_DATABASE_URL"])
    command.upgrade(config, "head")


async def run(args) -> int:
    from app import clock
    from evals.dataset import NOW, load_scenarios, load_utterances
    from evals.harness import gather_limited, new_tenant, now_label, run_conversation, run_utterance
    from evals.judge import Judge
    from evals.llm import ThrottledLLM, eval_client
    from evals.report import metrics, render, to_json
    from vaani_agent.config import get_agent_settings

    settings = get_agent_settings()
    if not settings.gemini_api_key:
        print("Set GEMINI_API_KEY to run the evals.", file=sys.stderr)
        return 2
    clock.now = lambda: NOW  # every run sees Monday 2 Nov 2026, 9:00 AM IST
    llm = ThrottledLLM(
        eval_client(settings.gemini_api_key), rpm=args.rpm, concurrency=args.concurrency
    )

    scenarios = load_scenarios()
    if args.only:
        scenarios = [s for s in scenarios if s.category in args.only]
    utterances = [] if args.skip_utterances else load_utterances()
    if args.limit:
        scenarios, utterances = scenarios[: args.limit], utterances[: args.limit]

    print(
        f"Running {len(scenarios)} conversations and {len(utterances)} utterances "
        f"on {settings.gemini_model} ...",
        file=sys.stderr,
    )
    conversations = await gather_limited(
        [run_conversation(s, i, llm=llm, settings=settings) for i, s in enumerate(scenarios)],
        args.concurrency,
    )
    if not args.skip_judge:
        judge = Judge(llm, args.judge_model or settings.gemini_model)
        await gather_limited([judge.grade(r) for r in conversations], args.concurrency)

    utterance_results = []
    if utterances:
        shared = await new_tenant("utterances")  # read-mostly; one clinic is enough
        utterance_results = await gather_limited(
            [run_utterance(u, shared, llm=llm, settings=settings) for u in utterances],
            args.concurrency,
        )

    rows = metrics(conversations, utterance_results, booking_target=args.fail_under)
    REPORTS.mkdir(exist_ok=True)
    markdown = render(
        conversations, utterance_results, rows, model=settings.gemini_model, when=now_label()
    )
    (REPORTS / "latest.md").write_text(markdown)
    (REPORTS / "latest.json").write_text(
        json.dumps(to_json(conversations, utterance_results, rows), ensure_ascii=False, indent=2)
    )
    print(markdown)
    print(f"{llm.calls} Gemini calls. Report: {REPORTS / 'latest.md'}", file=sys.stderr)

    booking = rows[0]
    if booking.value is not None and booking.value < args.fail_under:
        print(f"FAIL: booking success {booking.value:.1%} < {args.fail_under:.0%}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--only", nargs="+", help="conversation categories to run")
    parser.add_argument("--limit", type=int, help="run only the first N of each set")
    parser.add_argument("--skip-utterances", action="store_true")
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--judge-model", help="defaults to GEMINI_MODEL")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--rpm", type=int, default=60, help="max Gemini requests per minute")
    parser.add_argument("--fail-under", type=float, default=0.90, help="booking success gate")
    parser.add_argument("--pg", default=os.environ.get("EVAL_PG", "localhost:5435"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    configure_environment(args.pg)
    prepare_database(args.pg)
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

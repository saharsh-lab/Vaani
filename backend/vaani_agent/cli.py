"""Chat with a business's agent in the terminal (text-first milestone).

    python -m vaani_agent.cli --business sri-dental
    python -m vaani_agent.cli --business sri-dental --phone 9876543210   # like caller ID
    python -m vaani_agent.cli --list-models

Needs the API running (uvicorn app.main:app) and GEMINI_API_KEY in .env.
"""

import argparse
import asyncio
import statistics
import sys

import httpx
from google.genai import errors as genai_errors

from vaani_agent.api_client import VaaniApi
from vaani_agent.config import AgentSettings, get_agent_settings
from vaani_agent.runtime import AgentSession
from vaani_agent.tools import ToolContext

EXIT_WORDS = {"exit", "quit", "bye"}


def list_models(settings: AgentSettings) -> None:
    client = AgentSession.gemini_client(settings)  # keep a reference: the pager uses it
    for model in client.models.list():
        if "generateContent" in (model.supported_actions or []):
            print(model.name.removeprefix("models/"))


async def open_session(
    api: VaaniApi, settings: AgentSettings, slug: str, phone: str | None
) -> tuple[AgentSession, dict]:
    try:
        business = await api.resolve_business(slug)
    except httpx.ConnectError:
        sys.exit(f"Can't reach the API at {settings.api_base_url}. Start it: uvicorn app.main:app")
    except httpx.HTTPStatusError as exc:
        sys.exit(f"Couldn't load business {slug!r}: {exc.response.text}")
    api.set_business(business["id"])
    context = await api.context()
    conversation = await api.start_conversation("web_chat", customer_phone=phone)
    session = AgentSession(
        api=api,
        llm=AgentSession.gemini_client(settings),
        settings=settings,
        context=context,
        tool_context=ToolContext(
            conversation_id=conversation["id"],
            channel="web_chat",
            verified_phone=conversation["customer_phone"],
        ),
    )
    return session, context


def print_tool_calls(session: AgentSession, since: int) -> None:
    for content in session.history[since:]:
        for part in content.parts or []:
            if part.function_call:
                call = part.function_call
                print(f"        ⚙ {call.name}({dict(call.args or {})})")


def chat(slug: str, phone: str | None, show_tools: bool) -> None:
    settings = get_agent_settings()
    # input() runs between runner.run() calls, outside the event loop, so Ctrl-C
    # and Ctrl-D interrupt it normally.
    with asyncio.Runner() as runner:
        api = VaaniApi(settings.api_base_url, settings.agent_api_key)
        session = None
        try:
            session, context = runner.run(open_session(api, settings, slug, phone))
            print(f"\n{context['name']} · {settings.gemini_model} · 'bye' to end\n")
            print(f"agent › {context.get('greeting') or 'Hello, how can I help?'}\n")
            while True:
                user = input("you   › ").strip()
                if not user:
                    continue
                if user.lower() in EXIT_WORDS:
                    break
                seen = len(session.history)
                try:
                    answer = runner.run(session.reply(user))
                except genai_errors.APIError as exc:
                    if exc.code == 404:
                        sys.exit(
                            f"Model {settings.gemini_model!r} isn't available. "
                            "Run with --list-models and set GEMINI_MODEL in .env."
                        )
                    print(f"[gemini error {exc.code}: {exc.message}]\n")
                    continue
                if show_tools:
                    print_tool_calls(session, seen)
                print(f"agent › {answer}\n")
        except (EOFError, KeyboardInterrupt):
            print()
        finally:
            if session is not None:
                runner.run(session.end())
                if session.latencies_ms:
                    print(
                        f"{len(session.latencies_ms)} turns · outcome {session.outcome} · "
                        f"{session.input_tokens:,} in / {session.output_tokens:,} out tokens · "
                        f"₹{session.cost_inr:.4f} · median {statistics.median(session.latencies_ms):.0f} ms"
                    )
            runner.run(api.http.aclose())


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--business", default="sri-dental", help="business slug")
    parser.add_argument("--phone", help="treat this as the caller's verified number (caller ID)")
    parser.add_argument("--hide-tools", action="store_true", help="don't print tool calls")
    parser.add_argument("--list-models", action="store_true", help="list models your key can use")
    args = parser.parse_args()

    settings = get_agent_settings()
    if not settings.gemini_api_key:
        sys.exit("Set GEMINI_API_KEY in .env (free key: https://aistudio.google.com/apikey)")
    if args.list_models:
        list_models(settings)
    else:
        chat(args.business, args.phone, show_tools=not args.hide_tools)


if __name__ == "__main__":
    main()

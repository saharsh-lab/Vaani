"""Numbers from real conversations: the spec's metrics that need live traffic.

    python -m evals.calls                 # all businesses, all channels
    python -m evals.calls --business sri-dental --channel voice

Reads the database in ADMIN_DATABASE_URL (your dev or production database).
Reply latency for voice is the time from the caller stopping speaking to the
agent's first audio, saved by the voice worker on every reply.
"""

import argparse
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

STATS_SQL = text(
    """
    WITH convs AS (
      SELECT c.* FROM conversations c JOIN businesses b ON b.id = c.business_id
      WHERE (CAST(:slug AS text) IS NULL OR b.slug = :slug)
        AND (CAST(:channel AS text) IS NULL OR c.channel = :channel)
    )
    SELECT
      c.channel,
      count(*)                                            AS conversations,
      count(*) FILTER (WHERE c.ended_at IS NOT NULL)      AS ended,
      avg(c.handoff::int)                                 AS handoff_rate,
      sum(c.cost_inr) FILTER (WHERE c.ended_at IS NOT NULL)   AS cost_inr,
      sum(c.duration_s) FILTER (WHERE c.ended_at IS NOT NULL) AS duration_s,
      (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY m.latency_ms)
         FROM messages m JOIN convs c2 ON c2.id = m.conversation_id
        WHERE c2.channel = c.channel AND m.role = 'assistant' AND m.latency_ms IS NOT NULL) AS p50_ms,
      (SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY m.latency_ms)
         FROM messages m JOIN convs c2 ON c2.id = m.conversation_id
        WHERE c2.channel = c.channel AND m.role = 'assistant' AND m.latency_ms IS NOT NULL) AS p95_ms
    FROM convs c
    GROUP BY c.channel
    ORDER BY c.channel
    """
)

LANGUAGES_SQL = text(
    """
    SELECT coalesce(c.language, 'unknown') AS language, count(*) AS n
    FROM conversations c JOIN businesses b ON b.id = c.business_id
    WHERE (CAST(:slug AS text) IS NULL OR b.slug = :slug)
      AND (CAST(:channel AS text) IS NULL OR c.channel = :channel)
    GROUP BY 1 ORDER BY 2 DESC
    """
)


async def call_stats(
    session: AsyncSession, *, slug: str | None = None, channel: str | None = None
) -> dict:
    params = {"slug": slug, "channel": channel}
    channels = []
    for row in (await session.execute(STATS_SQL, params)).mappings():
        minutes = (row["duration_s"] or 0) / 60
        channels.append(
            {
                "channel": row["channel"],
                "conversations": row["conversations"],
                "ended": row["ended"],
                "handoff_rate": float(row["handoff_rate"] or 0),
                "p50_ms": row["p50_ms"],
                "p95_ms": row["p95_ms"],
                "cost_per_minute_inr": float(row["cost_inr"]) / minutes if minutes else None,
            }
        )
    languages = {r.language: r.n for r in await session.execute(LANGUAGES_SQL, params)}
    return {"channels": channels, "languages": languages}


def render(stats: dict) -> str:
    lines = [
        "| Channel | Conversations | Reply latency p50 / p95 | ₹ per minute | Handoff rate |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c in stats["channels"]:
        latency = f"{c['p50_ms']:,.0f} / {c['p95_ms']:,.0f} ms" if c["p50_ms"] is not None else "–"
        cost = f"₹{c['cost_per_minute_inr']:.2f}" if c["cost_per_minute_inr"] is not None else "–"
        lines.append(
            f"| {c['channel']} | {c['conversations']} | {latency} | {cost} | {c['handoff_rate']:.0%} |"
        )
    mix = ", ".join(f"{lang} {n}" for lang, n in stats["languages"].items()) or "–"
    return "\n".join(lines) + f"\n\nLanguages: {mix}\n"


async def main() -> None:
    from app.db import system_session

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--business", help="business slug")
    parser.add_argument("--channel", choices=["voice", "whatsapp", "web_chat"])
    args = parser.parse_args()
    async with system_session() as session:
        stats = await call_stats(session, slug=args.business, channel=args.channel)
    print(render(stats))


if __name__ == "__main__":
    asyncio.run(main())

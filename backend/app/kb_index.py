"""Embed knowledge-base chunks that don't have an embedding yet.

    python -m app.kb_index

Run it after seeding, after deploying to a new database, or if embedding failed
while an owner saved an FAQ (for example, the Gemini quota ran out).
"""

import asyncio

from sqlalchemy import select, text

from app.db import system_session
from app.models import KbChunk
from app.services import embeddings
from app.services.knowledge import embed_chunks


async def index_missing(batch: int = 100) -> int:
    if embeddings.get_embedder() is None:
        raise SystemExit("Set GEMINI_API_KEY to create embeddings.")
    done = 0
    while True:
        async with system_session() as session:
            pending = (
                await session.scalars(
                    select(KbChunk).where(text("kb_chunks.embedding IS NULL")).limit(batch)
                )
            ).all()
            if not pending:
                return done
            if await embed_chunks(session, list(pending)) == 0:
                raise SystemExit("Embedding failed; check the Gemini key and quota.")
            done += len(pending)


def main() -> None:
    print(f"Embedded {asyncio.run(index_missing())} chunks.")


if __name__ == "__main__":
    main()

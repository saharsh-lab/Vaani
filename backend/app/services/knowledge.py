"""search_knowledge.

For now this is keyword search on a Postgres full-text index. The agent is told to
search in English, since owners write FAQs in English. The RAG milestone adds
multilingual embeddings in kb_chunks.embedding (pgvector) and combines both scores.
"""

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import KnowledgeHit, KnowledgeOut

STOPWORDS = set(
    """a an and are can could do does for from have how i in is it me my of on or our
    please should tell that the there this to we what when where which who why will with
    you your yours""".split()
)

# Word characters plus the Indic Unicode blocks (Devanagari to Malayalam), whose
# vowel signs \w alone would split words on.
_NON_WORD = re.compile(r"[^\wऀ-ൿ]+")

SEARCH_SQL = text(
    """
    SELECT d.title, c.content, ts_rank_cd(c.tsv, q) AS rank
    FROM kb_chunks c
    JOIN kb_documents d ON d.id = c.document_id,
         to_tsquery('simple', :query) q
    WHERE c.tsv @@ q
    ORDER BY rank DESC
    LIMIT :limit
    """
)


def to_or_query(question: str) -> str | None:
    terms = [w for w in _NON_WORD.sub(" ", question.lower()).split() if w not in STOPWORDS]
    terms = [t for t in dict.fromkeys(terms) if len(t) > 1 or not t.isascii()]
    return " | ".join(terms) or None


async def search_knowledge(session: AsyncSession, question: str, limit: int = 3) -> KnowledgeOut:
    query = to_or_query(question)
    rows = (
        (await session.execute(SEARCH_SQL, {"query": query, "limit": limit})).all() if query else []
    )
    if not rows:
        return KnowledgeOut(
            results=[],
            note="Nothing in the knowledge base answers this. Say so and offer a callback.",
        )
    return KnowledgeOut(results=[KnowledgeHit(title=r.title, content=r.content) for r in rows])

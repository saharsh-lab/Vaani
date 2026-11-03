"""search_knowledge: hybrid keyword + semantic search over the business's FAQs and
uploaded documents.

- Keyword search (Postgres full text) is exact and needs no API.
- Semantic search (Gemini embeddings in pgvector) matches meaning across
  languages: "పార్కింగ్ ఉందా?" finds the English parking FAQ.

The two rankings are merged with reciprocal rank fusion. Semantic matches are
kept only above SIMILARITY_FLOOR and within RELATIVE_WINDOW of the best one.
Measured with gemini-embedding-001 on the demo FAQs: unrelated questions score
0.55-0.64 and relevant ones 0.59-0.75 (best match), so results below
SIMILARITY_STRONG come with a note asking the agent to judge relevance.
Without embeddings (no key, or the API fails) search is keyword-only.
"""

import logging
import re
import uuid

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KbChunk
from app.schemas import KnowledgeHit, KnowledgeOut
from app.services import embeddings

log = logging.getLogger(__name__)

SIMILARITY_FLOOR = 0.60
RELATIVE_WINDOW = 0.07  # drop lower-ranked semantic matches far below the best
SIMILARITY_STRONG = 0.65
RRF_K = 60
CANDIDATES = 10

STOPWORDS = set(
    """a an and are can could do does for from have how i in is it me my of on or our
    please should tell that the there this to we what when where which who why will with
    you your yours""".split()
)

# Word characters plus the Indic Unicode blocks (Devanagari to Malayalam), whose
# vowel signs \w alone would split words on.
_NON_WORD = re.compile(r"[^\wऀ-ൿ]+")

KEYWORD_SQL = text(
    """
    SELECT c.id, d.title, c.content
    FROM kb_chunks c
    JOIN kb_documents d ON d.id = c.document_id,
         to_tsquery('simple', :query) q
    WHERE c.tsv @@ q
    ORDER BY ts_rank_cd(c.tsv, q) DESC
    LIMIT :limit
    """
)

VECTOR_SQL = text(
    """
    SELECT c.id, d.title, c.content, 1 - (c.embedding <=> CAST(:vector AS vector)) AS similarity
    FROM kb_chunks c
    JOIN kb_documents d ON d.id = c.document_id
    WHERE c.embedding IS NOT NULL
    ORDER BY c.embedding <=> CAST(:vector AS vector)
    LIMIT :limit
    """
)


def to_or_query(question: str) -> str | None:
    terms = [w for w in _NON_WORD.sub(" ", question.lower()).split() if w not in STOPWORDS]
    terms = [t for t in dict.fromkeys(terms) if len(t) > 1 or not t.isascii()]
    return " | ".join(terms) or None


async def _semantic(session: AsyncSession, question: str) -> list:
    embedder = embeddings.get_embedder()
    if embedder is None:
        return []
    try:
        (vector,) = await embedder.embed([question], query=True)
    except Exception:
        log.warning("embedding the question failed; keyword search only", exc_info=True)
        return []
    # With row-level security filtering the index scan, keep scanning the HNSW
    # index until enough of this business's rows are found (pgvector >= 0.8;
    # an unknown setting on older versions is harmless).
    await session.execute(text("SELECT set_config('hnsw.iterative_scan', 'relaxed_order', true)"))
    rows = await session.execute(
        VECTOR_SQL, {"vector": embeddings.to_pgvector(vector), "limit": CANDIDATES}
    )
    rows = [r for r in rows if r.similarity >= SIMILARITY_FLOOR]
    if not rows:
        return []
    best = rows[0].similarity
    return [r for r in rows if r.similarity >= best - RELATIVE_WINDOW]


async def search_knowledge(session: AsyncSession, question: str, limit: int = 3) -> KnowledgeOut:
    query = to_or_query(question)
    keyword = (
        (await session.execute(KEYWORD_SQL, {"query": query, "limit": CANDIDATES})).all()
        if query
        else []
    )
    semantic = await _semantic(session, question)

    scores: dict[uuid.UUID, float] = {}
    hits: dict[uuid.UUID, KnowledgeHit] = {}
    for ranking in (keyword, semantic):
        for rank, row in enumerate(ranking):
            scores[row.id] = scores.get(row.id, 0.0) + 1 / (RRF_K + rank + 1)
            hits[row.id] = KnowledgeHit(title=row.title, content=row.content)
    if not scores:
        return KnowledgeOut(
            results=[],
            note="Nothing in the knowledge base answers this. Say so and offer a callback.",
        )

    best = sorted(scores, key=scores.get, reverse=True)[:limit]
    note = None
    if not keyword and max(r.similarity for r in semantic) < SIMILARITY_STRONG:
        note = (
            "These are weak matches. Use them only if they actually answer the question; "
            "otherwise say you don't know and offer a callback."
        )
    return KnowledgeOut(results=[hits[i] for i in best], note=note)


async def embed_chunks(session: AsyncSession, chunks: list[KbChunk]) -> int:
    """Store embeddings for these chunks. Returns how many were embedded (0 if
    embeddings are off or the API fails; `python -m app.kb_index` fills them later)."""
    embedder = embeddings.get_embedder()
    if embedder is None or not chunks:
        return 0
    try:
        vectors = await embedder.embed([c.content for c in chunks], query=False)
    except Exception:
        log.warning(
            "embedding %d chunks failed; run app.kb_index later", len(chunks), exc_info=True
        )
        return 0
    await session.execute(
        text("UPDATE kb_chunks SET embedding = CAST(:vector AS vector) WHERE id = :id"),
        [
            {"id": c.id, "vector": embeddings.to_pgvector(v)}
            for c, v in zip(chunks, vectors, strict=True)
        ],
    )
    return len(chunks)


async def replace_chunks(
    session: AsyncSession, business_id: uuid.UUID, document_id: uuid.UUID, texts: list[str]
) -> list[KbChunk]:
    """Replace a document's chunks and embed them."""
    await session.execute(delete(KbChunk).where(KbChunk.document_id == document_id))
    chunks = [KbChunk(business_id=business_id, document_id=document_id, content=t) for t in texts]
    session.add_all(chunks)
    await session.flush()
    await embed_chunks(session, chunks)
    return chunks

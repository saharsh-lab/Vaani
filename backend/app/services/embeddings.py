"""Text embeddings for knowledge-base search (Gemini, multilingual).

A Telugu or Hindi question finds the English FAQ that answers it. Without a
Gemini key, `get_embedder()` returns None and search falls back to keywords.
"""

from functools import lru_cache
from typing import Protocol

from google import genai
from google.genai import types

from vaani_agent.config import get_agent_settings

DIMENSIONS = 768  # matches kb_chunks.embedding vector(768)
BATCH = 100


class Embedder(Protocol):
    async def embed(self, texts: list[str], *, query: bool) -> list[list[float]]: ...


class GeminiEmbedder:
    def __init__(self, api_key: str, model: str) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def embed(self, texts: list[str], *, query: bool) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH):
            response = await self.client.aio.models.embed_content(
                model=self.model,
                contents=texts[start : start + BATCH],
                config=types.EmbedContentConfig(
                    output_dimensionality=DIMENSIONS,
                    task_type="RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT",
                ),
            )
            vectors += [e.values for e in response.embeddings]
        return vectors


@lru_cache
def _gemini() -> GeminiEmbedder | None:
    settings = get_agent_settings()
    if not settings.gemini_api_key:
        return None
    return GeminiEmbedder(settings.gemini_api_key, settings.embedding_model)


def get_embedder() -> Embedder | None:
    return _gemini()


def to_pgvector(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"

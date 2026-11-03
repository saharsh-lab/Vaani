"""Turning uploaded documents (PDF menus, price lists, policies) into search chunks."""

import io
import re

from pypdf import PdfReader


class UnreadableDocument(ValueError):
    pass


def extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise UnreadableDocument("That file isn't a readable PDF") from exc
    return "\n\n".join(p.strip() for p in pages if p.strip())


def chunk_text(text: str, max_chars: int = 1000, overlap: int = 150) -> list[str]:
    """Split on paragraphs, then sentences, into chunks of at most max_chars.
    Consecutive chunks share `overlap` characters so an answer that spans a
    boundary is still found whole in one of them."""
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []
    pieces: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = " ".join(paragraph.split())
        if len(paragraph) <= max_chars:
            pieces.append(paragraph)
            continue
        sentences = re.split(r"(?<=[.!?।])\s+", paragraph)
        for sentence in sentences:
            while len(sentence) > max_chars:  # a very long sentence: hard split
                pieces.append(sentence[:max_chars])
                sentence = sentence[max_chars:]
            pieces.append(sentence)

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + 1 + len(piece) > max_chars:
            chunks.append(current)
            current = current[-overlap:].lstrip() + " " + piece if overlap else piece
            current = current.strip()
        else:
            current = f"{current} {piece}".strip() if current else piece
    if current:
        chunks.append(current)
    return chunks

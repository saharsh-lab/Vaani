"""Knowledge base: hybrid keyword + semantic search, document uploads, and the
fallbacks when embeddings aren't available."""

import pytest
from sqlalchemy import text

from app.db import system_session
from app.kb_index import index_missing
from app.seed import DEMO_PASSWORDS
from app.services import embeddings
from app.services.documents import chunk_text, extract_pdf_text
from tests.conftest import OWNER, browser, signed_in
from tests.fakes import FakeEmbedder, make_pdf


@pytest.fixture
def fake_embedder(monkeypatch):
    fake = FakeEmbedder()
    monkeypatch.setattr(embeddings, "get_embedder", lambda: fake)
    return fake


async def ask(client, question: str) -> dict:
    return (await client.post("/v1/tools/search_knowledge", json={"question": question})).json()


async def embedded_chunks() -> int:
    async with system_session() as s:
        return await s.scalar(text("SELECT count(*) FROM kb_chunks WHERE embedding IS NOT NULL"))


# Search --------------------------------------------------------------------------------


async def test_telugu_question_finds_the_english_faq(client, fake_embedder):
    assert (await ask(client, "పార్కింగ్ ఉందా?"))["results"] == []  # before indexing: no keyword overlap
    assert await index_missing() == 8
    found = await ask(client, "పార్కింగ్ ఉందా?")
    assert found["results"][0]["title"] == "Location and parking"
    assert found["note"] is None


async def test_unrelated_questions_find_nothing(client, fake_embedder):
    await index_missing()
    found = await ask(client, "Do you sell bicycles?")
    assert found["results"] == [] and "Say so" in found["note"]


async def test_weak_matches_come_with_a_warning(client, fake_embedder):
    await index_missing()
    found = await ask(client, "పార్కింగ్ bicycle cricket")  # partly about parking
    assert found["results"][0]["title"] == "Location and parking"
    assert "weak matches" in found["note"]


async def test_embedding_outage_falls_back_to_keywords(client, monkeypatch):
    monkeypatch.setattr(embeddings, "get_embedder", lambda: FakeEmbedder(fail=True))
    found = await ask(client, "Is there parking?")
    assert found["results"][0]["title"] == "Location and parking"


async def test_without_a_key_search_is_keyword_only(client):
    assert embeddings.get_embedder() is None  # tests run without GEMINI_API_KEY
    assert (await ask(client, "Can I pay by UPI?"))["results"][0]["title"] == "Payment methods"


# Owner edits and uploads -------------------------------------------------------------------


async def test_new_faq_is_embedded_on_save(owner, client, fake_embedder):
    r = await owner.post(
        "/v1/dashboard/faqs",
        json={
            "title": "Whitening",
            "content": "Q: Do you do teeth whitening? A: Yes, 4000 rupees.",
        },
    )
    assert r.status_code == 201 and r.json()["source_type"] == "faq"
    found = await ask(client, "పళ్ళు తెల్లగా చేస్తారా?")  # Telugu, no shared words
    assert found["results"][0]["title"] == "Whitening"


async def test_owner_uploads_a_pdf_price_list(owner, client, fake_embedder):
    pdf = make_pdf(
        ["Price list 2026.", "Dental implant: 25000 rupees.", "Teeth whitening: 4000 rupees."]
    )
    r = await owner.post(
        "/v1/dashboard/faqs/upload",
        files={"file": ("Price list.pdf", pdf, "application/pdf")},
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["title"] == "Price list" and doc["source_type"] == "pdf" and doc["chunks"] == 1
    assert "25000 rupees" in doc["content"]

    found = await ask(client, "how much is a dental implant")
    assert any("25000" in hit["content"] for hit in found["results"])
    edit = await owner.put(
        f"/v1/dashboard/faqs/{doc['id']}", json={"title": "Price list", "content": "New prices"}
    )
    assert edit.status_code == 409  # replace by uploading again


async def test_uploads_are_checked(owner, staff):
    word = await owner.post(
        "/v1/dashboard/faqs/upload", files={"file": ("menu.docx", b"PK..", "application/msword")}
    )
    assert word.status_code == 415
    huge = await owner.post(
        "/v1/dashboard/faqs/upload",
        files={"file": ("big.txt", b"a" * (5 * 1024 * 1024 + 1), "text/plain")},
    )
    assert huge.status_code == 413
    scanned = await owner.post(
        "/v1/dashboard/faqs/upload", files={"file": ("scan.pdf", make_pdf([]), "application/pdf")}
    )
    assert scanned.status_code == 422 and "No text" in scanned.json()["detail"]
    broken = await owner.post(
        "/v1/dashboard/faqs/upload",
        files={"file": ("x.pdf", b"%PDF-1.4 garbage", "application/pdf")},
    )
    assert broken.status_code == 422
    text_file = await owner.post(
        "/v1/dashboard/faqs/upload",
        files={"file": ("policies.txt", b"Refunds within 7 days.", "text/plain")},
    )
    assert text_file.status_code == 201 and text_file.json()["source_type"] == "text"
    assert (
        await staff.post("/v1/dashboard/faqs/upload", files={"file": ("a.txt", b"x", "text/plain")})
    ).status_code == 403


# Documents and chunking ---------------------------------------------------------------------


def test_pdf_text_extraction():
    assert "Dental implant: 25000 rupees." in extract_pdf_text(
        make_pdf(["Dental implant: 25000 rupees."])
    )


def test_chunks_stay_small_and_overlap():
    paragraph = " ".join(f"Sentence number {i} about clinic policy." for i in range(120))
    chunks = chunk_text(paragraph, max_chars=500, overlap=100)
    assert len(chunks) > 5 and all(len(c) <= 500 + 100 for c in chunks)
    assert chunks[1][:40] in chunks[0]  # the next chunk starts inside the previous one
    assert chunk_text("Short FAQ.\n\nAnother one.") == ["Short FAQ. Another one."]
    assert chunk_text("   ") == []


# Accounts ------------------------------------------------------------------------------------


async def test_change_password(owner):
    wrong = await owner.post(
        "/v1/auth/password",
        json={"current_password": "nope-nope", "new_password": "new-password-1"},
    )
    assert wrong.status_code == 403
    ok = await owner.post(
        "/v1/auth/password",
        json={"current_password": DEMO_PASSWORDS["owner"], "new_password": "new-password-1"},
    )
    assert ok.status_code == 204
    async with browser() as c:
        old = await c.post(
            "/v1/auth/login", json={"email": OWNER, "password": DEMO_PASSWORDS["owner"]}
        )
        assert old.status_code == 401
    async with signed_in(OWNER, "new-password-1") as c:
        assert (await c.get("/v1/dashboard/me")).status_code == 200

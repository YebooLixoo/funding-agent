"""Phase 3 tests: Document upload, keyword extraction, chat."""

from __future__ import annotations

import io
import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from web.database import Base, get_db
from web.routers import auth, users, keywords, documents, chat

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


test_app = FastAPI()
test_app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
prefix = "/api/v1"
for r in [auth, users, keywords, documents, chat]:
    test_app.include_router(r.router, prefix=prefix)

test_app.dependency_overrides[get_db] = override_get_db

# Set the session factory for background tasks to use test DB
from web.routers.documents import set_session_factory
set_session_factory(TestSession)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def register_and_auth(client: AsyncClient, email="doc@example.com") -> dict:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "securepass123", "full_name": "Doc User"},
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# ─── Document Upload ──────────────────────────────────────────────────


class TestDocumentUpload:
    async def test_upload_txt_file(self, client: AsyncClient):
        headers = await register_and_auth(client)
        content = b"I am a researcher studying machine learning and autonomous vehicles."
        res = await client.post(
            "/api/v1/documents",
            headers=headers,
            files={"file": ("resume.txt", io.BytesIO(content), "text/plain")},
            data={"file_type": "resume"},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["filename"] == "resume.txt"
        assert data["file_type"] == "resume"
        assert data["upload_status"] == "pending"

    async def test_upload_invalid_file_type(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.post(
            "/api/v1/documents",
            headers=headers,
            files={"file": ("test.txt", io.BytesIO(b"test"), "text/plain")},
            data={"file_type": "invalid"},
        )
        assert res.status_code == 400

    async def test_list_documents(self, client: AsyncClient):
        headers = await register_and_auth(client)
        # Upload two docs
        await client.post(
            "/api/v1/documents",
            headers=headers,
            files={"file": ("doc1.txt", io.BytesIO(b"content1"), "text/plain")},
            data={"file_type": "resume"},
        )
        await client.post(
            "/api/v1/documents",
            headers=headers,
            files={"file": ("doc2.txt", io.BytesIO(b"content2"), "text/plain")},
            data={"file_type": "paper"},
        )

        res = await client.get("/api/v1/documents", headers=headers)
        assert res.status_code == 200
        assert len(res.json()) == 2

    async def test_get_document(self, client: AsyncClient):
        headers = await register_and_auth(client)
        upload_res = await client.post(
            "/api/v1/documents",
            headers=headers,
            files={"file": ("test.txt", io.BytesIO(b"content"), "text/plain")},
            data={"file_type": "cv"},
        )
        doc_id = upload_res.json()["id"]

        res = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
        assert res.status_code == 200
        assert res.json()["id"] == doc_id

    async def test_delete_document(self, client: AsyncClient):
        headers = await register_and_auth(client)
        upload_res = await client.post(
            "/api/v1/documents",
            headers=headers,
            files={"file": ("test.txt", io.BytesIO(b"content"), "text/plain")},
            data={"file_type": "resume"},
        )
        doc_id = upload_res.json()["id"]

        res = await client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
        assert res.status_code == 204

        # Verify deleted
        res2 = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
        assert res2.status_code == 404

    async def test_reprocess_document(self, client: AsyncClient):
        headers = await register_and_auth(client)
        upload_res = await client.post(
            "/api/v1/documents",
            headers=headers,
            files={"file": ("test.txt", io.BytesIO(b"content"), "text/plain")},
            data={"file_type": "resume"},
        )
        doc_id = upload_res.json()["id"]

        res = await client.post(f"/api/v1/documents/{doc_id}/reprocess", headers=headers)
        assert res.status_code == 200
        assert res.json()["upload_status"] == "pending"

    async def test_document_isolation(self, client: AsyncClient):
        """Documents should be per-user."""
        h1 = await register_and_auth(client, "user1@example.com")
        h2 = await register_and_auth(client, "user2@example.com")

        # User 1 uploads
        await client.post(
            "/api/v1/documents",
            headers=h1,
            files={"file": ("u1.txt", io.BytesIO(b"user1"), "text/plain")},
            data={"file_type": "resume"},
        )

        # User 2 should see nothing
        res = await client.get("/api/v1/documents", headers=h2)
        assert len(res.json()) == 0

        # User 1 should see one
        res = await client.get("/api/v1/documents", headers=h1)
        assert len(res.json()) == 1


# ─── Document Processing Service ─────────────────────────────────────


class TestDocumentProcessing:
    def test_extract_text_from_txt(self, tmp_path):
        from web.services.document_processor import extract_text_from_file

        f = tmp_path / "test.txt"
        f.write_text("Hello world, I study machine learning.")
        text = extract_text_from_file(str(f), "resume")
        assert "machine learning" in text

    def test_extract_text_from_pdf(self, tmp_path):
        """Test PDF extraction using PyMuPDF."""
        import pymupdf

        # Create a minimal PDF
        pdf_path = tmp_path / "test.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Research in autonomous vehicles and deep learning")
        doc.save(str(pdf_path))
        doc.close()

        from web.services.document_processor import extract_text_from_pdf
        text = extract_text_from_pdf(str(pdf_path))
        assert "autonomous vehicles" in text
        assert "deep learning" in text


# ─── Chat ─────────────────────────────────────────────────────────────


class TestChat:
    async def test_chat_history_empty(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.get("/api/v1/chat/history", headers=headers)
        assert res.status_code == 200
        assert res.json() == []

    async def test_chat_action_parsing(self):
        """Test that suggested actions JSON is correctly parsed."""
        from web.services.chat import parse_suggested_actions

        # Valid JSON block
        content = """Here are my suggestions:

```json
{
  "actions": [
    {"type": "add", "keyword": "robotics", "category": "domain"},
    {"type": "remove", "keyword": "biology", "category": "exclusion"}
  ]
}
```

Let me know if you want to apply these."""

        result = parse_suggested_actions(content)
        assert result is not None
        assert len(result["actions"]) == 2
        assert result["actions"][0]["keyword"] == "robotics"

    async def test_chat_action_parsing_no_json(self):
        from web.services.chat import parse_suggested_actions
        result = parse_suggested_actions("Just a regular response without any actions.")
        assert result is None

    async def test_apply_actions_not_found(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.post(
            "/api/v1/chat/apply-actions",
            headers=headers,
            json={"message_id": str(uuid.uuid4())},
        )
        assert res.status_code == 404


# ─── Keyword Extractor ────────────────────────────────────────────────


class TestKeywordExtractor:
    async def test_extraction_prompt_structure(self):
        """Verify the extraction prompt contains required categories."""
        from web.services.keyword_extractor import EXTRACTION_PROMPT
        assert "primary" in EXTRACTION_PROMPT
        assert "domain" in EXTRACTION_PROMPT
        assert "career" in EXTRACTION_PROMPT
        assert "faculty" in EXTRACTION_PROMPT

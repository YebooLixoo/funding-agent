"""Phase 1 tests: Backend foundation, auth, opportunities, keywords."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from web.database import Base, get_db
from web.models.opportunity import Opportunity
from web.routers import auth, users, opportunities, keywords

# Use SQLite for testing (no PostgreSQL needed)
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


# Build a test app that doesn't try to connect to PostgreSQL
test_app = FastAPI()
test_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
prefix = "/api/v1"
test_app.include_router(auth.router, prefix=prefix)
test_app.include_router(users.router, prefix=prefix)
test_app.include_router(opportunities.router, prefix=prefix)
test_app.include_router(keywords.router, prefix=prefix)


@test_app.get("/health")
async def health():
    return {"status": "ok"}


test_app.dependency_overrides[get_db] = override_get_db


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


@pytest_asyncio.fixture
async def seed_opportunities():
    """Seed some test opportunities into the DB."""
    async with TestSession() as session:
        for i in range(5):
            opp = Opportunity(
                composite_id=f"test_source_{i}",
                source="test_source",
                source_id=str(i),
                title=f"Test Opportunity {i}: Machine Learning for Transportation",
                description=f"Description for opportunity {i} about AI and deep learning.",
                url=f"https://example.com/opp/{i}",
                source_type="government" if i % 2 == 0 else "industry",
                deadline=f"2026-06-{15 + i:02d}",
                funding_amount="$500,000",
                keywords=["machine learning", "transportation"],
                summary=f"Summary of opportunity {i}.",
            )
            session.add(opp)
        await session.commit()


# ─── Health ───────────────────────────────────────────────────────────


class TestHealth:
    async def test_health(self, client: AsyncClient):
        res = await client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}


# ─── Auth ─────────────────────────────────────────────────────────────


class TestAuth:
    async def test_register(self, client: AsyncClient):
        res = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "password": "securepass123",
                "full_name": "Test User",
                "institution": "MIT",
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_register_duplicate_email(self, client: AsyncClient):
        body = {
            "email": "dup@example.com",
            "password": "securepass123",
            "full_name": "User One",
        }
        res1 = await client.post("/api/v1/auth/register", json=body)
        assert res1.status_code == 201
        res2 = await client.post("/api/v1/auth/register", json=body)
        assert res2.status_code == 400
        assert "already registered" in res2.json()["detail"]

    async def test_register_short_password(self, client: AsyncClient):
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": "short@example.com", "password": "abc", "full_name": "Short Pass"},
        )
        assert res.status_code == 400
        assert "8 characters" in res.json()["detail"]

    async def test_login(self, client: AsyncClient):
        # Register first
        await client.post(
            "/api/v1/auth/register",
            json={"email": "login@example.com", "password": "securepass123", "full_name": "Login User"},
        )
        # Login
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@example.com", "password": "securepass123"},
        )
        assert res.status_code == 200
        assert "access_token" in res.json()

    async def test_login_wrong_password(self, client: AsyncClient):
        await client.post(
            "/api/v1/auth/register",
            json={"email": "wrong@example.com", "password": "securepass123", "full_name": "User"},
        )
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "wrong@example.com", "password": "wrongpass"},
        )
        assert res.status_code == 401

    async def test_refresh_token(self, client: AsyncClient):
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": "refresh@example.com", "password": "securepass123", "full_name": "User"},
        )
        refresh_token = reg.json()["refresh_token"]
        res = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert res.status_code == 200
        assert "access_token" in res.json()

    async def test_refresh_invalid_token(self, client: AsyncClient):
        res = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid-token"},
        )
        assert res.status_code == 401


# ─── Users ────────────────────────────────────────────────────────────


class TestUsers:
    async def _auth_headers(self, client: AsyncClient, email="user@example.com") -> dict:
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123", "full_name": "Test User", "institution": "MIT"},
        )
        token = res.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_get_me(self, client: AsyncClient):
        headers = await self._auth_headers(client)
        res = await client.get("/api/v1/users/me", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == "user@example.com"
        assert data["full_name"] == "Test User"
        assert data["institution"] == "MIT"

    async def test_update_me(self, client: AsyncClient):
        headers = await self._auth_headers(client)
        res = await client.put(
            "/api/v1/users/me",
            headers=headers,
            json={"full_name": "Updated Name", "department": "CS"},
        )
        assert res.status_code == 200
        assert res.json()["full_name"] == "Updated Name"
        assert res.json()["department"] == "CS"

    async def test_delete_me(self, client: AsyncClient):
        headers = await self._auth_headers(client)
        res = await client.delete("/api/v1/users/me", headers=headers)
        assert res.status_code == 204
        # Verify user is gone
        res2 = await client.get("/api/v1/users/me", headers=headers)
        assert res2.status_code == 401

    async def test_unauthenticated(self, client: AsyncClient):
        res = await client.get("/api/v1/users/me")
        assert res.status_code in (401, 403)  # No bearer token


# ─── Opportunities ────────────────────────────────────────────────────


class TestOpportunities:
    async def _auth_headers(self, client: AsyncClient) -> dict:
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": "opp@example.com", "password": "securepass123", "full_name": "Opp User"},
        )
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    async def test_list_empty(self, client: AsyncClient):
        headers = await self._auth_headers(client)
        res = await client.get("/api/v1/opportunities", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_with_data(self, client: AsyncClient, seed_opportunities):
        headers = await self._auth_headers(client)
        res = await client.get("/api/v1/opportunities", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 5
        assert len(data["items"]) == 5

    async def test_pagination(self, client: AsyncClient, seed_opportunities):
        headers = await self._auth_headers(client)
        res = await client.get("/api/v1/opportunities?page=1&page_size=2", headers=headers)
        data = res.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["total_pages"] == 3

    async def test_filter_by_source_type(self, client: AsyncClient, seed_opportunities):
        headers = await self._auth_headers(client)
        res = await client.get("/api/v1/opportunities?source_type=government", headers=headers)
        data = res.json()
        assert all(item["source_type"] == "government" for item in data["items"])

    async def test_search(self, client: AsyncClient, seed_opportunities):
        headers = await self._auth_headers(client)
        res = await client.get("/api/v1/opportunities?search=Machine+Learning", headers=headers)
        data = res.json()
        assert data["total"] == 5  # All have "Machine Learning" in title

    async def test_get_single(self, client: AsyncClient, seed_opportunities):
        headers = await self._auth_headers(client)
        # Get list first to get an ID
        list_res = await client.get("/api/v1/opportunities", headers=headers)
        opp_id = list_res.json()["items"][0]["id"]
        res = await client.get(f"/api/v1/opportunities/{opp_id}", headers=headers)
        assert res.status_code == 200
        assert res.json()["id"] == opp_id

    async def test_get_not_found(self, client: AsyncClient):
        headers = await self._auth_headers(client)
        fake_id = str(uuid.uuid4())
        res = await client.get(f"/api/v1/opportunities/{fake_id}", headers=headers)
        assert res.status_code == 404

    async def test_bookmark(self, client: AsyncClient, seed_opportunities):
        headers = await self._auth_headers(client)
        list_res = await client.get("/api/v1/opportunities", headers=headers)
        opp_id = list_res.json()["items"][0]["id"]

        # Bookmark
        res = await client.post(f"/api/v1/opportunities/{opp_id}/bookmark", headers=headers)
        assert res.status_code == 200

        # Get and verify bookmarked
        opp_res = await client.get(f"/api/v1/opportunities/{opp_id}", headers=headers)
        assert opp_res.json()["is_bookmarked"] is True

        # Unbookmark
        res = await client.delete(f"/api/v1/opportunities/{opp_id}/bookmark", headers=headers)
        assert res.status_code == 200

    async def test_dismiss(self, client: AsyncClient, seed_opportunities):
        headers = await self._auth_headers(client)
        list_res = await client.get("/api/v1/opportunities", headers=headers)
        opp_id = list_res.json()["items"][0]["id"]
        res = await client.post(f"/api/v1/opportunities/{opp_id}/dismiss", headers=headers)
        assert res.status_code == 200

    async def test_bookmarks_list(self, client: AsyncClient, seed_opportunities):
        headers = await self._auth_headers(client)
        list_res = await client.get("/api/v1/opportunities", headers=headers)
        opp_id = list_res.json()["items"][0]["id"]

        # Bookmark one
        await client.post(f"/api/v1/opportunities/{opp_id}/bookmark", headers=headers)

        # List bookmarks
        res = await client.get("/api/v1/opportunities/bookmarks/list", headers=headers)
        assert res.status_code == 200
        assert len(res.json()) == 1


# ─── Keywords ─────────────────────────────────────────────────────────


class TestKeywords:
    async def _auth_headers(self, client: AsyncClient) -> dict:
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": "kw@example.com", "password": "securepass123", "full_name": "KW User"},
        )
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    async def test_list_empty(self, client: AsyncClient):
        headers = await self._auth_headers(client)
        res = await client.get("/api/v1/keywords", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["primary"] == []
        assert data["domain"] == []

    async def test_add_keyword(self, client: AsyncClient):
        headers = await self._auth_headers(client)
        res = await client.post(
            "/api/v1/keywords",
            headers=headers,
            json={"keyword": "machine learning", "category": "primary"},
        )
        assert res.status_code == 201
        assert res.json()["keyword"] == "machine learning"
        assert res.json()["category"] == "primary"

    async def test_add_duplicate_keyword(self, client: AsyncClient):
        headers = await self._auth_headers(client)
        body = {"keyword": "deep learning", "category": "primary"}
        await client.post("/api/v1/keywords", headers=headers, json=body)
        res = await client.post("/api/v1/keywords", headers=headers, json=body)
        assert res.status_code == 409

    async def test_add_invalid_category(self, client: AsyncClient):
        headers = await self._auth_headers(client)
        res = await client.post(
            "/api/v1/keywords",
            headers=headers,
            json={"keyword": "test", "category": "invalid"},
        )
        assert res.status_code == 400

    async def test_update_keyword(self, client: AsyncClient):
        headers = await self._auth_headers(client)
        create_res = await client.post(
            "/api/v1/keywords",
            headers=headers,
            json={"keyword": "test kw", "category": "domain", "weight": 1.0},
        )
        kw_id = create_res.json()["id"]
        res = await client.put(
            f"/api/v1/keywords/{kw_id}",
            headers=headers,
            json={"weight": 0.5},
        )
        assert res.status_code == 200
        assert res.json()["weight"] == 0.5

    async def test_delete_keyword(self, client: AsyncClient):
        headers = await self._auth_headers(client)
        create_res = await client.post(
            "/api/v1/keywords",
            headers=headers,
            json={"keyword": "to delete", "category": "custom"},
        )
        kw_id = create_res.json()["id"]
        res = await client.delete(f"/api/v1/keywords/{kw_id}", headers=headers)
        assert res.status_code == 204

    async def test_bulk_add(self, client: AsyncClient):
        headers = await self._auth_headers(client)
        res = await client.post(
            "/api/v1/keywords/bulk",
            headers=headers,
            json={
                "keywords": [
                    {"keyword": "ai", "category": "primary"},
                    {"keyword": "robotics", "category": "domain"},
                    {"keyword": "early career", "category": "career"},
                ]
            },
        )
        assert res.status_code == 201
        assert len(res.json()) == 3

    async def test_list_grouped(self, client: AsyncClient):
        headers = await self._auth_headers(client)
        await client.post(
            "/api/v1/keywords/bulk",
            headers=headers,
            json={
                "keywords": [
                    {"keyword": "ml", "category": "primary"},
                    {"keyword": "nlp", "category": "primary"},
                    {"keyword": "biology", "category": "domain"},
                ]
            },
        )
        res = await client.get("/api/v1/keywords", headers=headers)
        data = res.json()
        assert len(data["primary"]) == 2
        assert len(data["domain"]) == 1

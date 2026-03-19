"""Phase 4 tests: Email preferences, fetch config, email scheduler, deadlines."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from web.database import Base, get_db
from web.models.opportunity import Opportunity
from web.routers import auth, users, opportunities, keywords, email, fetch, scoring

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
for r in [auth, users, opportunities, keywords, email, fetch, scoring]:
    test_app.include_router(r.router, prefix=prefix)

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


async def register_and_auth(client: AsyncClient, email_addr="p4@example.com") -> dict:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email_addr, "password": "securepass123", "full_name": "P4 User"},
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest_asyncio.fixture
async def seed_opps_with_deadlines():
    async with TestSession() as session:
        for i in range(5):
            opp = Opportunity(
                composite_id=f"dl_src_{i}",
                source="nsf",
                source_id=f"dl{i}",
                title=f"Deadline Opportunity {i}",
                description="AI research grant",
                source_type="government",
                deadline=f"2026-{6 + i:02d}-15",
            )
            session.add(opp)
        await session.commit()


# ─── Email Preferences ───────────────────────────────────────────────


class TestEmailPreferences:
    async def test_get_default_preferences(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.get("/api/v1/email/preferences", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["is_subscribed"] is True
        assert data["frequency"] == "weekly"
        assert data["day_of_week"] == 4  # Thursday
        assert data["min_relevance_score"] == 0.3

    async def test_update_preferences(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.put(
            "/api/v1/email/preferences",
            headers=headers,
            json={"frequency": "daily", "min_relevance_score": 0.5, "deadline_lookahead_days": 14},
        )
        assert res.status_code == 200
        assert res.json()["frequency"] == "daily"
        assert res.json()["min_relevance_score"] == 0.5
        assert res.json()["deadline_lookahead_days"] == 14

    async def test_invalid_frequency(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.put(
            "/api/v1/email/preferences",
            headers=headers,
            json={"frequency": "hourly"},
        )
        assert res.status_code == 400

    async def test_unsubscribe(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.post("/api/v1/email/unsubscribe", headers=headers)
        assert res.status_code == 200

        # Verify
        pref = await client.get("/api/v1/email/preferences", headers=headers)
        assert pref.json()["is_subscribed"] is False

    async def test_email_history_empty(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.get("/api/v1/email/history", headers=headers)
        assert res.status_code == 200
        assert res.json() == []

    async def test_send_test(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.post("/api/v1/email/send-test", headers=headers)
        assert res.status_code == 200

        # Check it appears in history
        hist = await client.get("/api/v1/email/history", headers=headers)
        assert len(hist.json()) == 1

    async def test_preferences_per_user(self, client: AsyncClient):
        h1 = await register_and_auth(client, "u1@example.com")
        h2 = await register_and_auth(client, "u2@example.com")

        await client.put("/api/v1/email/preferences", headers=h1, json={"frequency": "daily"})
        await client.put("/api/v1/email/preferences", headers=h2, json={"frequency": "biweekly"})

        r1 = await client.get("/api/v1/email/preferences", headers=h1)
        r2 = await client.get("/api/v1/email/preferences", headers=h2)
        assert r1.json()["frequency"] == "daily"
        assert r2.json()["frequency"] == "biweekly"


# ─── Fetch Config ────────────────────────────────────────────────────


class TestFetchConfig:
    async def test_get_default_config(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.get("/api/v1/fetch/config", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["fetch_frequency"] == "weekly"
        assert data["sources_enabled"] is not None
        assert data["sources_enabled"]["nsf"] is True

    async def test_update_config(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.put(
            "/api/v1/fetch/config",
            headers=headers,
            json={"sources_enabled": {"nsf": True, "nih": False}, "fetch_frequency": "daily"},
        )
        assert res.status_code == 200
        assert res.json()["fetch_frequency"] == "daily"
        assert res.json()["sources_enabled"]["nih"] is False

    async def test_invalid_frequency(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.put(
            "/api/v1/fetch/config",
            headers=headers,
            json={"fetch_frequency": "hourly"},
        )
        assert res.status_code == 400

    async def test_trigger_fetch(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.post("/api/v1/fetch/trigger", headers=headers)
        assert res.status_code == 200
        assert res.json()["status"] == "triggered"

        # last_fetched_at should be set
        status = await client.get("/api/v1/fetch/status", headers=headers)
        assert status.json()["last_fetched_at"] is not None

    async def test_fetch_status(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.get("/api/v1/fetch/status", headers=headers)
        assert res.status_code == 200
        assert "fetch_frequency" in res.json()


# ─── Deadlines ────────────────────────────────────────────────────────


class TestDeadlines:
    async def test_opportunities_sorted_by_deadline(
        self, client: AsyncClient, seed_opps_with_deadlines
    ):
        headers = await register_and_auth(client)
        res = await client.get(
            "/api/v1/opportunities?sort_by=deadline&sort_order=asc&page_size=10",
            headers=headers,
        )
        assert res.status_code == 200
        items = res.json()["items"]
        assert len(items) == 5
        # Verify sorted ascending
        deadlines = [i["deadline"] for i in items if i["deadline"]]
        assert deadlines == sorted(deadlines)


# ─── Email Scheduler Service ─────────────────────────────────────────


class TestEmailSchedulerService:
    async def test_get_users_due_for_email(self):
        """Test the email scheduler finds users who need emails."""
        from web.services.email_scheduler import get_users_due_for_email

        async with TestSession() as db:
            # No users, should return empty
            users = await get_users_due_for_email(db)
            assert users == []


# ─── Fetcher Service ─────────────────────────────────────────────────


class TestFetcherService:
    async def test_store_fetched_opportunity(self):
        from web.services.fetcher import store_fetched_opportunity

        async with TestSession() as db:
            opp = await store_fetched_opportunity(
                db,
                source="test",
                source_id="123",
                title="Test Grant",
                description="A test grant about AI",
                url="https://example.com",
            )
            assert opp is not None
            assert opp.composite_id == "test_123"
            await db.commit()

            # Duplicate should return None
            opp2 = await store_fetched_opportunity(
                db,
                source="test",
                source_id="123",
                title="Test Grant Dup",
                description="duplicate",
                url="https://example.com",
            )
            assert opp2 is None

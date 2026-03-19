"""Phase 2 tests: Scoring, filter settings, profile, keyword management integration."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from web.database import Base, get_db
from web.models.opportunity import Opportunity
from web.models.keyword import UserKeyword
from web.routers import auth, users, opportunities, keywords, filter_settings, scoring

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
for r in [auth, users, opportunities, keywords, filter_settings, scoring]:
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


async def register_and_auth(client: AsyncClient, email="phase2@example.com") -> dict:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "securepass123", "full_name": "Phase2 User", "institution": "MIT"},
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest_asyncio.fixture
async def seed_opportunities():
    async with TestSession() as session:
        for i in range(10):
            opp = Opportunity(
                composite_id=f"src_{i}",
                source="nsf",
                source_id=str(i),
                title=f"Opportunity {i}: {'Machine Learning for Transportation' if i < 5 else 'Biology Research Grant'}",
                description=f"Description about {'AI and deep learning' if i < 5 else 'genomics and CRISPR'}",
                url=f"https://example.com/{i}",
                source_type="government",
                deadline=f"2026-07-{10 + i:02d}",
                summary=f"Summary about {'autonomous vehicles' if i < 5 else 'molecular biology'}",
            )
            session.add(opp)
        await session.commit()


# ─── Filter Settings ─────────────────────────────────────────────────


class TestFilterSettings:
    async def test_get_default_settings(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.get("/api/v1/filter-settings", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["keyword_threshold"] == 0.3
        assert data["llm_threshold"] == 0.5
        assert data["use_llm_filter"] is True

    async def test_update_settings(self, client: AsyncClient):
        headers = await register_and_auth(client)
        # First get to create default
        await client.get("/api/v1/filter-settings", headers=headers)
        # Update
        res = await client.put(
            "/api/v1/filter-settings",
            headers=headers,
            json={"keyword_threshold": 0.5, "use_llm_filter": False},
        )
        assert res.status_code == 200
        assert res.json()["keyword_threshold"] == 0.5
        assert res.json()["use_llm_filter"] is False

    async def test_settings_persist(self, client: AsyncClient):
        headers = await register_and_auth(client)
        await client.put(
            "/api/v1/filter-settings",
            headers=headers,
            json={"keyword_threshold": 0.7},
        )
        res = await client.get("/api/v1/filter-settings", headers=headers)
        assert res.json()["keyword_threshold"] == 0.7


# ─── Scoring ──────────────────────────────────────────────────────────


class TestScoring:
    async def test_rescore_no_keywords(self, client: AsyncClient, seed_opportunities):
        headers = await register_and_auth(client)
        res = await client.post("/api/v1/scoring/rescore", headers=headers)
        assert res.status_code == 200
        assert res.json()["scored_count"] == 10

    async def test_rescore_with_keywords(self, client: AsyncClient, seed_opportunities):
        headers = await register_and_auth(client)
        # Add keywords
        await client.post(
            "/api/v1/keywords/bulk",
            headers=headers,
            json={
                "keywords": [
                    {"keyword": "machine learning", "category": "primary"},
                    {"keyword": "transportation", "category": "domain"},
                    {"keyword": "autonomous vehicles", "category": "domain"},
                ]
            },
        )
        # Rescore
        res = await client.post("/api/v1/scoring/rescore", headers=headers)
        assert res.status_code == 200
        assert res.json()["scored_count"] == 10

        # Check that opportunities now have scores
        opps = await client.get("/api/v1/opportunities?page_size=10", headers=headers)
        items = opps.json()["items"]
        # At least some should have non-zero scores (the ML/transportation ones)
        scored_items = [i for i in items if i.get("relevance_score") and i["relevance_score"] > 0]
        assert len(scored_items) > 0

    async def test_scores_are_personalized(self, client: AsyncClient, seed_opportunities):
        # User 1: ML researcher
        h1 = await register_and_auth(client, "ml@example.com")
        await client.post(
            "/api/v1/keywords/bulk",
            headers=h1,
            json={"keywords": [{"keyword": "machine learning", "category": "primary"}]},
        )
        await client.post("/api/v1/scoring/rescore", headers=h1)

        # User 2: Biology researcher
        h2 = await register_and_auth(client, "bio@example.com")
        await client.post(
            "/api/v1/keywords/bulk",
            headers=h2,
            json={"keywords": [{"keyword": "biology", "category": "primary"}, {"keyword": "genomics", "category": "domain"}]},
        )
        await client.post("/api/v1/scoring/rescore", headers=h2)

        # Get scores for user 1
        opps1 = await client.get("/api/v1/opportunities?page_size=10", headers=h1)
        # Get scores for user 2
        opps2 = await client.get("/api/v1/opportunities?page_size=10", headers=h2)

        # Scores should be different (personalized)
        scores1 = {i["id"]: i.get("relevance_score", 0) for i in opps1.json()["items"]}
        scores2 = {i["id"]: i.get("relevance_score", 0) for i in opps2.json()["items"]}

        # They should not be identical
        different = any(scores1.get(k, 0) != scores2.get(k, 0) for k in scores1)
        assert different, "Scores should be personalized per user"


# ─── Profile Update ──────────────────────────────────────────────────


class TestProfileUpdate:
    async def test_full_profile_update(self, client: AsyncClient):
        headers = await register_and_auth(client)
        res = await client.put(
            "/api/v1/users/me",
            headers=headers,
            json={
                "full_name": "Dr. Jane Smith",
                "institution": "Stanford",
                "department": "Computer Science",
                "position": "Assistant Professor",
                "research_summary": "I study machine learning for autonomous systems.",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["full_name"] == "Dr. Jane Smith"
        assert data["institution"] == "Stanford"
        assert data["department"] == "Computer Science"
        assert data["position"] == "Assistant Professor"
        assert "autonomous systems" in data["research_summary"]


# ─── Keyword Workflow ─────────────────────────────────────────────────


class TestKeywordWorkflow:
    async def test_add_keywords_across_categories(self, client: AsyncClient):
        headers = await register_and_auth(client)

        # Add to multiple categories
        await client.post("/api/v1/keywords", headers=headers, json={"keyword": "deep learning", "category": "primary"})
        await client.post("/api/v1/keywords", headers=headers, json={"keyword": "robotics", "category": "domain"})
        await client.post("/api/v1/keywords", headers=headers, json={"keyword": "early career", "category": "career"})
        await client.post("/api/v1/keywords", headers=headers, json={"keyword": "biomedical", "category": "exclusion"})

        res = await client.get("/api/v1/keywords", headers=headers)
        data = res.json()
        assert len(data["primary"]) == 1
        assert len(data["domain"]) == 1
        assert len(data["career"]) == 1
        assert len(data["exclusion"]) == 1
        assert data["primary"][0]["keyword"] == "deep learning"
        assert data["exclusion"][0]["keyword"] == "biomedical"

    async def test_toggle_and_rescore(self, client: AsyncClient, seed_opportunities):
        headers = await register_and_auth(client)

        # Add keyword
        res = await client.post(
            "/api/v1/keywords",
            headers=headers,
            json={"keyword": "machine learning", "category": "primary"},
        )
        kw_id = res.json()["id"]

        # Score with keyword active
        await client.post("/api/v1/scoring/rescore", headers=headers)
        opps = await client.get("/api/v1/opportunities?page_size=10", headers=headers)
        active_scores = {i["id"]: i.get("relevance_score", 0) for i in opps.json()["items"]}

        # Disable keyword
        await client.put(f"/api/v1/keywords/{kw_id}", headers=headers, json={"is_active": False})

        # Rescore
        await client.post("/api/v1/scoring/rescore", headers=headers)
        opps2 = await client.get("/api/v1/opportunities?page_size=10", headers=headers)
        inactive_scores = {i["id"]: i.get("relevance_score", 0) for i in opps2.json()["items"]}

        # Scores should change when keyword is toggled
        assert active_scores != inactive_scores

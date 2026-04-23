"""Shared pytest fixtures for the test suite.

Provides a fresh in-memory SQLite ``db_session`` per test plus an ``admin_user``
fixture. Used by Tasks 5-15 of the consolidation plan.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import web.models  # noqa: F401 — register all model tables on Base
from web.database import Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session(monkeypatch) -> AsyncSession:
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Make any service code that imports ``async_session`` share this engine.
    # This lets tests that drive multi-session services (e.g., fetch_runner)
    # verify state via the fixture's ``db_session`` handle.
    import web.database as _db_mod
    monkeypatch.setattr(_db_mod, "async_session", Session, raising=False)
    try:
        import web.services.fetch_runner as _fr_mod
        monkeypatch.setattr(_fr_mod, "async_session", Session, raising=False)
    except ImportError:
        # fetch_runner may not exist yet during earlier-task imports
        pass
    try:
        import web.services.email_dispatcher as _ed_mod
        monkeypatch.setattr(_ed_mod, "async_session", Session, raising=False)
    except ImportError:
        # email_dispatcher may not exist yet during earlier-task imports
        pass
    try:
        import scripts.migrate_state_db as _mig_mod
        monkeypatch.setattr(_mig_mod, "async_session", Session, raising=False)
    except ImportError:
        # migrate_state_db may not exist yet during earlier-task imports
        pass

    async with Session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def admin_user(db_session):
    from web.models.user import User

    u = User(
        email="admin@test",
        password_hash="x",
        full_name="Admin",
        is_admin=True,
        is_active=True,
    )
    db_session.add(u)
    await db_session.flush()
    return u

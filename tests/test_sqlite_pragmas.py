"""Verify SQLite WAL mode and busy_timeout are applied on every connection.

Uses a tempfile-backed SQLite database (not :memory:) because in-memory
SQLite databases ignore PRAGMA journal_mode=WAL and stay at "memory".
"""

from __future__ import annotations

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from web.config import get_settings


@pytest.mark.asyncio
async def test_wal_and_busy_timeout_enabled(tmp_path):
    """A fresh SQLite engine, with the same connect-time PRAGMA listener
    used in web.database, should report journal_mode=wal and a non-zero
    busy_timeout."""
    settings = get_settings()
    db_path = tmp_path / "pragma_test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _conn_record):  # pragma: no cover - exercised via connect
        cur = dbapi_conn.cursor()
        if settings.sqlite_wal_mode:
            cur.execute("PRAGMA journal_mode=WAL")
        cur.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
        cur.close()

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as s:
            mode = (await s.execute(text("PRAGMA journal_mode"))).scalar()
            timeout = (await s.execute(text("PRAGMA busy_timeout"))).scalar()
    finally:
        await engine.dispose()

    assert mode == "wal", f"expected wal, got {mode!r}"
    assert timeout >= 5000, f"expected >=5000, got {timeout!r}"

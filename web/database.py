from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from web.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=settings.debug)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _conn_record):
    """Apply WAL mode and busy_timeout to every new SQLite connection.

    No-op for non-SQLite databases (Postgres, etc.).
    """
    if "sqlite" not in settings.database_url:
        return
    cur = dbapi_conn.cursor()
    if settings.sqlite_wal_mode:
        cur.execute("PRAGMA journal_mode=WAL")
    cur.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
    cur.close()


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

"""Seed the platform's opportunities table from the internal pipeline's SQLite DB.

Usage:
    uv run python -m web.services.seed_opportunities

This performs a one-time import of all opportunities from data/state.db
into the platform's PostgreSQL database. Safe to run multiple times
(skips duplicates by composite_id).
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.database import async_session, engine, Base
from web.models.opportunity import Opportunity


SQLITE_PATH = Path("data/state.db")


def read_internal_opportunities() -> list[dict]:
    """Read all opportunities from the internal SQLite DB."""
    if not SQLITE_PATH.exists():
        print(f"Internal DB not found at {SQLITE_PATH}")
        return []

    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        """
        SELECT composite_id, source, title, url, description, summary,
               deadline, posted_date, funding_amount, keywords,
               relevance_score, source_type, fetched_at
        FROM seen_opportunities
        ORDER BY fetched_at DESC
        """
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    rows = read_internal_opportunities()
    if not rows:
        print("No opportunities to seed.")
        return

    print(f"Found {len(rows)} opportunities in internal DB")
    imported = 0
    skipped = 0

    async with async_session() as session:
        for row in rows:
            # Check if already exists
            result = await session.execute(
                select(Opportunity).where(Opportunity.composite_id == row["composite_id"])
            )
            if result.scalar_one_or_none():
                skipped += 1
                continue

            # Extract source_id from composite_id (format: "source_sourceId")
            parts = row["composite_id"].split("_", 1)
            source_id = parts[1] if len(parts) > 1 else row["composite_id"]

            # Parse keywords from comma-separated string
            keywords = None
            if row.get("keywords"):
                keywords = [k.strip() for k in row["keywords"].split(",") if k.strip()]

            opp = Opportunity(
                composite_id=row["composite_id"],
                source=row["source"],
                source_id=source_id,
                title=row["title"],
                description=row.get("description"),
                url=row.get("url"),
                source_type=row.get("source_type"),
                deadline=row.get("deadline"),
                posted_date=row.get("posted_date"),
                funding_amount=row.get("funding_amount"),
                keywords=keywords,
                summary=row.get("summary"),
            )
            session.add(opp)
            imported += 1

        await session.commit()

    print(f"Seeded {imported} opportunities ({skipped} already existed)")


if __name__ == "__main__":
    asyncio.run(seed())

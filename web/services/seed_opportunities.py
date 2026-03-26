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

    # Migrate: add opportunity_status column if missing (older DBs)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(seen_opportunities)").fetchall()}
    if "opportunity_status" not in columns:
        conn.execute("ALTER TABLE seen_opportunities ADD COLUMN opportunity_status TEXT DEFAULT 'open'")
        conn.commit()

    cursor = conn.execute(
        """
        SELECT composite_id, source, title, url, description, summary,
               deadline, posted_date, funding_amount, keywords,
               relevance_score, source_type, opportunity_status, status, fetched_at
        FROM seen_opportunities
        ORDER BY fetched_at DESC
        """
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


async def seed(link_to_email: str | None = None):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    rows = read_internal_opportunities()
    if not rows:
        print("No opportunities to seed.")
        return

    # Skip opportunities that were filtered out by the internal pipeline
    rows = [r for r in rows if r.get("status") != "filtered_out"]

    print(f"Found {len(rows)} opportunities in internal DB")
    imported = 0
    skipped = 0

    async with async_session() as session:
        # Resolve user_id if linking to an email
        user_id = None
        if link_to_email:
            from web.models.user import User
            result = await session.execute(
                select(User).where(User.email == link_to_email)
            )
            user = result.scalar_one_or_none()
            if user:
                user_id = user.id
                print(f"Linking opportunities to user: {user.email} ({user_id})")
            else:
                print(f"Warning: user {link_to_email} not found, seeding without link")

        for row in rows:
            # Check if already exists
            result = await session.execute(
                select(Opportunity).where(Opportunity.composite_id == row["composite_id"])
            )
            existing = result.scalar_one_or_none()
            if existing:
                # Update link if user_id provided and not yet linked
                if user_id and not existing.fetched_for_user_id:
                    existing.fetched_for_user_id = user_id
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
                opportunity_status=row.get("opportunity_status", "open"),
                fetched_for_user_id=user_id,
            )
            session.add(opp)
            imported += 1

        await session.commit()

    print(f"Seeded {imported} opportunities ({skipped} already existed)")


if __name__ == "__main__":
    import sys
    email = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(seed(link_to_email=email))

"""One-time migration: legacy ``data/state.db`` (sqlite3) → platform DB (ORM).

Copies opportunities, emailed-flag deliveries (for the admin user), fetch history,
email history, and source-bootstrap state from the internal pipeline's SQLite
database into the platform database. After this runs successfully, ``state.db``
can be archived; the platform DB is the single source of truth.

The migration is idempotent: re-running it produces zero new rows in the
opportunity, delivery, and bootstrap tables. ``fetch_history`` and
``email_history`` use a "skip first N already-existing rows" check based on
count — adequate for a one-shot migration.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from src.models import Opportunity as OppDC
from web.config import get_settings
from web.database import async_session
from web.models.fetch_history import FetchHistory
from web.models.email_pref import UserEmailHistory
from web.models.source_bootstrap import SourceBootstrap
from web.models.user import User
from web.models.user_email_delivery import UserEmailDelivery
from web.services.opportunity_writer import upsert_opportunity


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _parse_dt_legacy(raw) -> datetime | None:
    """Same as ``_parse_dt`` but tolerant of non-string inputs (None, bytes)."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _parse_keywords_legacy(raw) -> list:
    """Decode keywords stored as JSON string in legacy state.db."""
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw else []
        except (ValueError, TypeError):
            return []
    if isinstance(raw, (list, tuple)):
        return list(raw)
    return []


async def migrate(state_db_path: Path, admin_email: str) -> dict:
    """Idempotent migration of state.db → platform DB.

    Returns counts of newly-inserted rows per table.
    """
    if not state_db_path.exists():
        return {
            "opps": 0,
            "deliveries": 0,
            "fetch_history": 0,
            "email_history": 0,
            "bootstrap": 0,
        }

    conn = sqlite3.connect(str(state_db_path))
    conn.row_factory = sqlite3.Row

    counts = {
        "opps": 0,
        "deliveries": 0,
        "fetch_history": 0,
        "email_history": 0,
        "bootstrap": 0,
    }

    async with async_session() as s:
        admin = (
            await s.execute(
                select(User).where(User.email == admin_email, User.is_admin.is_(True))
            )
        ).scalar_one()

        # --- opportunities + deliveries ---
        for r in conn.execute("SELECT * FROM seen_opportunities"):
            # Recover source_id from composite_id (format: "<source>_<source_id>")
            composite = r["composite_id"]
            prefix = r["source"] + "_"
            source_id = composite[len(prefix):] if composite.startswith(prefix) else composite

            deadline_dt = _parse_dt_legacy(r["deadline"])
            posted_dt = _parse_dt_legacy(r["posted_date"])
            kw_list = _parse_keywords_legacy(r["keywords"])

            dc = OppDC(
                source=r["source"],
                source_id=source_id,
                title=r["title"],
                description=r["description"] or "",
                url=r["url"],
                source_type=r["source_type"],
                summary=r["summary"] or "",
                relevance_score=r["relevance_score"] or 0.0,
                opportunity_status=r["opportunity_status"] or "open",
                deadline_type=r["deadline_type"] or "fixed",
                resource_type=r["resource_type"],
                resource_provider=r["resource_provider"],
                resource_scale=r["resource_scale"],
                allocation_details=r["allocation_details"],
                eligibility=r["eligibility"],
                access_url=r["access_url"],
                funding_amount=r["funding_amount"],
                deadline=deadline_dt,
                posted_date=posted_dt,
                keywords=kw_list,
            )
            row, was_new = await upsert_opportunity(s, dc)
            if was_new:
                counts["opps"] += 1
                # Preserve legacy ``fetched_at`` for the history page month
                # grouping. ``upsert_opportunity`` defaults this to NOW();
                # overwrite back to the legacy timestamp when known.
                legacy_fetched = _parse_dt_legacy(r["fetched_at"])
                if legacy_fetched is not None:
                    row.fetched_at = legacy_fetched

            if r["status"] == "emailed":
                exists = (
                    await s.execute(
                        select(UserEmailDelivery).where(
                            UserEmailDelivery.user_id == admin.id,
                            UserEmailDelivery.opportunity_id == row.id,
                        )
                    )
                ).scalar_one_or_none()
                if not exists:
                    s.add(
                        UserEmailDelivery(
                            user_id=admin.id,
                            opportunity_id=row.id,
                            sent_at=_parse_dt(r["fetched_at"]) or datetime.utcnow(),
                        )
                    )
                    counts["deliveries"] += 1

        # --- fetch_history (idempotent by row-count: skip first N already-present) ---
        existing_fh_count = len(
            (await s.execute(select(FetchHistory))).scalars().all()
        )
        legacy_fh = list(conn.execute("SELECT * FROM fetch_history"))
        for r in legacy_fh[existing_fh_count:]:
            s.add(
                FetchHistory(
                    source=r["source"],
                    fetch_window_start=_parse_dt(r["fetch_window_start"]),
                    fetch_window_end=_parse_dt(r["fetch_window_end"]),
                    success=bool(r["success"]),
                    count=r["count"],
                    error_msg=r["error_msg"],
                )
            )
            counts["fetch_history"] += 1

        # --- email_history → UserEmailHistory for admin ---
        existing_eh_count = len(
            (
                await s.execute(
                    select(UserEmailHistory).where(UserEmailHistory.user_id == admin.id)
                )
            )
            .scalars()
            .all()
        )
        legacy_eh = list(conn.execute("SELECT * FROM email_history"))
        for r in legacy_eh[existing_eh_count:]:
            s.add(
                UserEmailHistory(
                    user_id=admin.id,
                    sent_at=_parse_dt(r["sent_at"]) or datetime.utcnow(),
                    opportunity_count=r["opportunity_count"],
                    success=bool(r["success"]),
                    error_msg=r["error_msg"],
                )
            )
            counts["email_history"] += 1

        # --- source_bootstrap (PK is source_name → insert-if-missing) ---
        for r in conn.execute("SELECT * FROM source_bootstrap"):
            exists = (
                await s.execute(
                    select(SourceBootstrap).where(
                        SourceBootstrap.source_name == r["source_name"]
                    )
                )
            ).scalar_one_or_none()
            if not exists:
                s.add(
                    SourceBootstrap(
                        source_name=r["source_name"],
                        source_type=r["source_type"],
                        bootstrapped_at=_parse_dt(r["bootstrapped_at"])
                        or datetime.utcnow(),
                    )
                )
                counts["bootstrap"] += 1

        await s.commit()

    conn.close()
    return counts


def main():
    settings = get_settings()
    if not settings.admin_email:
        print("ERROR: ADMIN_EMAIL not set", file=sys.stderr)
        sys.exit(2)
    summary = asyncio.run(migrate(Path("data/state.db"), settings.admin_email))
    print("Migration complete:", summary)


if __name__ == "__main__":
    main()

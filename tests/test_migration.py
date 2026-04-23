import sqlite3
import pytest
from pathlib import Path
from datetime import datetime
from sqlalchemy import select

from scripts.migrate_state_db import migrate
from web.models.opportunity import Opportunity
from web.models.user_email_delivery import UserEmailDelivery
from web.models.fetch_history import FetchHistory
from web.models.email_pref import UserEmailHistory
from web.models.source_bootstrap import SourceBootstrap


def _build_legacy_state_db(path: Path):
    """Build a minimal state.db matching the legacy schema."""
    conn = sqlite3.connect(str(path))
    conn.executescript("""
    CREATE TABLE seen_opportunities (
        composite_id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        source_type TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        description TEXT,
        summary TEXT,
        deadline TEXT,
        posted_date TEXT,
        funding_amount TEXT,
        keywords TEXT,
        relevance_score REAL DEFAULT 0.0,
        opportunity_status TEXT DEFAULT 'open',
        deadline_type TEXT DEFAULT 'fixed',
        resource_type TEXT,
        resource_provider TEXT,
        resource_scale TEXT,
        allocation_details TEXT,
        eligibility TEXT,
        access_url TEXT,
        status TEXT DEFAULT 'pending_email',
        fetched_at TEXT NOT NULL
    );
    CREATE TABLE fetch_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        fetch_window_start TEXT NOT NULL,
        fetch_window_end TEXT NOT NULL,
        success INTEGER NOT NULL DEFAULT 1,
        count INTEGER NOT NULL DEFAULT 0,
        error_msg TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE email_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sent_at TEXT NOT NULL,
        opportunity_count INTEGER NOT NULL DEFAULT 0,
        success INTEGER NOT NULL DEFAULT 1,
        error_msg TEXT
    );
    CREATE TABLE source_bootstrap (
        source_name TEXT PRIMARY KEY,
        source_type TEXT NOT NULL,
        bootstrapped_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)
    # Two opps: one emailed, one pending
    conn.execute("""
        INSERT INTO seen_opportunities VALUES
        ('nsf_X1','nsf','government','ML Research Grant','https://e.com/1',
         'description','summary',NULL,NULL,NULL,NULL,0.7,'open','fixed',
         NULL,NULL,NULL,NULL,NULL,NULL,'emailed','2026-01-01T00:00:00')
    """)
    conn.execute("""
        INSERT INTO seen_opportunities VALUES
        ('nih_Y1','nih','government','AI Grant','https://e.com/2',
         'description','summary',NULL,NULL,NULL,NULL,0.6,'open','fixed',
         NULL,NULL,NULL,NULL,NULL,NULL,'pending_email','2026-01-02T00:00:00')
    """)
    conn.execute("""
        INSERT INTO fetch_history VALUES (
            NULL, 'all', '2026-01-01T12:00:00', '2026-01-08T12:00:00',
            1, 5, NULL, '2026-01-08T12:00:00'
        )
    """)
    conn.execute("""
        INSERT INTO email_history VALUES (
            NULL, '2026-01-08T20:00:00', 5, 1, NULL
        )
    """)
    conn.execute("""
        INSERT INTO source_bootstrap VALUES (
            'nsf', 'government', '2026-01-01T00:00:00', '2026-01-01T00:00:00'
        )
    """)
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_migration_copies_opps_emails_history_bootstrap(tmp_path, db_session, admin_user):
    sd = tmp_path / "state.db"
    _build_legacy_state_db(sd)

    summary = await migrate(state_db_path=sd, admin_email=admin_user.email)

    assert summary["opps"] == 2
    assert summary["deliveries"] == 1  # only the 'emailed' opp
    assert summary["fetch_history"] == 1
    assert summary["email_history"] == 1
    assert summary["bootstrap"] == 1

    # Verify in DB
    opps = (await db_session.execute(select(Opportunity))).scalars().all()
    assert len(opps) == 2
    composite_ids = {o.composite_id for o in opps}
    assert composite_ids == {"nsf_X1", "nih_Y1"}

    deliveries = (await db_session.execute(select(UserEmailDelivery))).scalars().all()
    assert len(deliveries) == 1
    assert deliveries[0].user_id == admin_user.id

    fh = (await db_session.execute(select(FetchHistory))).scalars().all()
    assert len(fh) == 1 and fh[0].count == 5

    eh = (await db_session.execute(select(UserEmailHistory))).scalars().all()
    assert len(eh) == 1 and eh[0].user_id == admin_user.id

    sb = (await db_session.execute(select(SourceBootstrap))).scalars().all()
    assert len(sb) == 1 and sb[0].source_name == "nsf"


@pytest.mark.asyncio
async def test_migration_idempotent(tmp_path, db_session, admin_user):
    """Running twice doesn't double-write deliveries or duplicate opps."""
    sd = tmp_path / "state.db"
    _build_legacy_state_db(sd)

    await migrate(state_db_path=sd, admin_email=admin_user.email)
    summary2 = await migrate(state_db_path=sd, admin_email=admin_user.email)

    # Second run inserts no new opps (dedup) and no new deliveries
    assert summary2["opps"] == 0
    assert summary2["deliveries"] == 0

    opps = (await db_session.execute(select(Opportunity))).scalars().all()
    assert len(opps) == 2
    deliveries = (await db_session.execute(select(UserEmailDelivery))).scalars().all()
    assert len(deliveries) == 1


@pytest.mark.asyncio
async def test_migration_missing_state_db_returns_zeros(tmp_path, db_session, admin_user):
    """If state.db doesn't exist, return all-zeros summary instead of crashing."""
    summary = await migrate(state_db_path=tmp_path / "nope.db", admin_email=admin_user.email)
    assert summary == {"opps": 0, "deliveries": 0, "fetch_history": 0, "email_history": 0, "bootstrap": 0}

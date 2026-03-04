"""SQLite state management: dedup, fetch history, email history."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from src.models import Opportunity

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_opportunities (
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
    status TEXT DEFAULT 'pending_email',
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fetch_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    fetch_window_start TEXT NOT NULL,
    fetch_window_end TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 1,
    count INTEGER NOT NULL DEFAULT 0,
    error_msg TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS email_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at TEXT NOT NULL,
    opportunity_count INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 1,
    error_msg TEXT
);
"""


class StateDB:
    """SQLite database for opportunity tracking and deduplication."""

    def __init__(self, db_path: str = "data/state.db") -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- Opportunity operations ---

    def is_seen(self, composite_id: str) -> bool:
        """Check if an opportunity has already been stored."""
        row = self.conn.execute(
            "SELECT 1 FROM seen_opportunities WHERE composite_id = ?", (composite_id,)
        ).fetchone()
        return row is not None

    def store_opportunity(self, opp: Opportunity) -> bool:
        """Store an opportunity. Returns False if already exists."""
        if self.is_seen(opp.composite_id):
            return False
        self.conn.execute(
            """INSERT INTO seen_opportunities
            (composite_id, source, source_type, title, url, description, summary,
             deadline, posted_date, funding_amount, keywords, relevance_score, status, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_email', ?)""",
            (
                opp.composite_id,
                opp.source,
                opp.source_type,
                opp.title,
                opp.url,
                opp.description,
                opp.summary,
                opp.deadline.isoformat() if opp.deadline else None,
                opp.posted_date.isoformat() if opp.posted_date else None,
                opp.funding_amount,
                ",".join(opp.keywords),
                opp.relevance_score,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()
        return True

    def get_pending_opportunities(self) -> list[dict]:
        """Get all opportunities with status 'pending_email'."""
        rows = self.conn.execute(
            "SELECT * FROM seen_opportunities WHERE status = 'pending_email' ORDER BY source_type, source"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_upcoming_deadlines(self, days: int = 30) -> list[dict]:
        """Get opportunities with deadlines within the next N days."""
        now = datetime.now(timezone.utc).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        rows = self.conn.execute(
            """SELECT * FROM seen_opportunities
            WHERE deadline IS NOT NULL AND deadline >= ? AND deadline <= ?
            ORDER BY deadline ASC""",
            (now, future),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_emailed(self, composite_ids: list[str]) -> None:
        """Mark opportunities as emailed."""
        self.conn.executemany(
            "UPDATE seen_opportunities SET status = 'emailed' WHERE composite_id = ?",
            [(cid,) for cid in composite_ids],
        )
        self.conn.commit()

    def cleanup_old(self, days: int = 90) -> int:
        """Remove entries older than N days. Returns count deleted."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cursor = self.conn.execute(
            "DELETE FROM seen_opportunities WHERE fetched_at < ?", (cutoff,)
        )
        self.conn.commit()
        return cursor.rowcount

    # --- Fetch history operations ---

    def record_fetch(
        self,
        source: str,
        window_start: datetime,
        window_end: datetime,
        success: bool,
        count: int = 0,
        error_msg: Optional[str] = None,
    ) -> None:
        """Record a fetch run."""
        self.conn.execute(
            """INSERT INTO fetch_history
            (source, fetch_window_start, fetch_window_end, success, count, error_msg, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                source,
                window_start.isoformat(),
                window_end.isoformat(),
                1 if success else 0,
                count,
                error_msg,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def get_last_successful_fetch_end(self, source: str = "all") -> Optional[datetime]:
        """Get the end time of the last successful fetch for gap-free tracking."""
        if source == "all":
            row = self.conn.execute(
                "SELECT MAX(fetch_window_end) as last_end FROM fetch_history WHERE success = 1"
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT MAX(fetch_window_end) as last_end FROM fetch_history WHERE success = 1 AND source = ?",
                (source,),
            ).fetchone()
        if row and row["last_end"]:
            return datetime.fromisoformat(row["last_end"])
        return None

    # --- Email history operations ---

    def record_email(
        self,
        count: int,
        success: bool,
        error_msg: Optional[str] = None,
    ) -> None:
        """Record an email send."""
        self.conn.execute(
            """INSERT INTO email_history (sent_at, opportunity_count, success, error_msg)
            VALUES (?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                count,
                1 if success else 0,
                error_msg,
            ),
        )
        self.conn.commit()

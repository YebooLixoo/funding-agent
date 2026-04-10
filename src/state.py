"""SQLite state management: dedup, fetch history, email history."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from src.models import Opportunity, next_quarter_deadline
from src.utils import normalize_url

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

CREATE TABLE IF NOT EXISTS source_bootstrap (
    source_name TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    bootstrapped_at TEXT NOT NULL,
    created_at TEXT NOT NULL
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
        self._migrate()

    def _migrate(self) -> None:
        """Add columns that may not exist in older databases."""
        cursor = self.conn.execute("PRAGMA table_info(seen_opportunities)")
        columns = {row[1] for row in cursor.fetchall()}
        if "opportunity_status" not in columns:
            self.conn.execute(
                "ALTER TABLE seen_opportunities ADD COLUMN opportunity_status TEXT DEFAULT 'open'"
            )
            self.conn.commit()
            logger.info("Migrated: added opportunity_status column")
        if "deadline_type" not in columns:
            self.conn.execute(
                "ALTER TABLE seen_opportunities ADD COLUMN deadline_type TEXT DEFAULT 'fixed'"
            )
            self.conn.commit()
            logger.info("Migrated: added deadline_type column")
        # Compute resource fields
        for col in ("resource_type", "resource_provider", "resource_scale",
                     "allocation_details", "eligibility", "access_url"):
            if col not in columns:
                self.conn.execute(
                    f"ALTER TABLE seen_opportunities ADD COLUMN {col} TEXT"
                )
                self.conn.commit()
                logger.info(f"Migrated: added {col} column")

    def seed_bootstrap(self, known_sources: list[tuple[str, str]]) -> None:
        """Seed source_bootstrap table for existing DBs on first upgrade.

        Called once after migration. If the table is empty but fetch_history
        has records (meaning the pipeline has run before), mark all known
        sources as already bootstrapped to prevent re-fetching everything.
        """
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM source_bootstrap").fetchone()
        if row["cnt"] > 0:
            return  # Already seeded

        has_history = self.conn.execute(
            "SELECT 1 FROM fetch_history WHERE success = 1 LIMIT 1"
        ).fetchone()
        if not has_history:
            return  # Fresh install — all sources should bootstrap

        now_iso = datetime.now(timezone.utc).isoformat()
        for name, stype in known_sources:
            self.conn.execute(
                """INSERT OR IGNORE INTO source_bootstrap
                (source_name, source_type, bootstrapped_at, created_at)
                VALUES (?, ?, ?, ?)""",
                (name, stype, now_iso, now_iso),
            )
        self.conn.commit()
        logger.info(
            f"Bootstrap migration: marked {len(known_sources)} existing sources "
            f"as bootstrapped"
        )

    def close(self) -> None:
        self.conn.close()

    # --- Opportunity operations ---

    def is_seen(self, composite_id: str) -> bool:
        """Check if an opportunity has already been stored."""
        row = self.conn.execute(
            "SELECT 1 FROM seen_opportunities WHERE composite_id = ?", (composite_id,)
        ).fetchone()
        return row is not None

    def is_url_seen(self, url: str) -> bool:
        """Check if any stored opportunity has the same normalized URL."""
        if not url:
            return False
        norm = normalize_url(url)
        rows = self.conn.execute(
            "SELECT url FROM seen_opportunities"
        ).fetchall()
        for row in rows:
            if normalize_url(row["url"]) == norm:
                return True
        return False

    def is_title_similar(self, title: str, threshold: float = 0.80) -> bool:
        """Check if any stored opportunity has a similar title (cross-source dedup).

        Uses normalized title comparison with SequenceMatcher for fuzzy matching.
        """
        import re
        from difflib import SequenceMatcher

        def normalize_title(t: str) -> str:
            t = t.lower().strip()
            t = re.sub(r'[^\w\s]', '', t)  # Remove punctuation
            t = re.sub(r'\s+', ' ', t)     # Collapse whitespace
            return t

        norm_new = normalize_title(title)
        if len(norm_new) < 10:  # Too short to match meaningfully
            return False

        rows = self.conn.execute("SELECT title FROM seen_opportunities").fetchall()
        for row in rows:
            norm_existing = normalize_title(row["title"])
            # Check SequenceMatcher similarity
            ratio = SequenceMatcher(None, norm_new, norm_existing).ratio()
            if ratio >= threshold:
                logger.debug(f"Cross-source dedup: '{title[:60]}' matches existing (similarity={ratio:.2f})")
                return True
            # Also check substring containment (short title inside long title)
            shorter, longer = sorted([norm_new, norm_existing], key=len)
            if len(shorter) >= 15 and shorter in longer:
                logger.debug(f"Cross-source dedup (substring): '{title[:60]}' contained in existing")
                return True
        return False

    def store_opportunity(self, opp: Opportunity) -> bool:
        """Store an opportunity. Returns False if already exists (by ID or URL)."""
        if self.is_seen(opp.composite_id):
            return False
        if self.is_url_seen(opp.url):
            logger.debug(f"URL-dedup: {opp.title[:60]} (url={opp.url})")
            return False
        if self.is_title_similar(opp.title):
            logger.debug(f"Title-dedup: {opp.title[:60]}")
            return False
        self.conn.execute(
            """INSERT INTO seen_opportunities
            (composite_id, source, source_type, title, url, description, summary,
             deadline, posted_date, funding_amount, keywords, relevance_score,
             opportunity_status, deadline_type,
             resource_type, resource_provider, resource_scale,
             allocation_details, eligibility, access_url,
             status, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_email', ?)""",
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
                opp.opportunity_status,
                opp.deadline_type,
                opp.resource_type,
                opp.resource_provider,
                opp.resource_scale,
                opp.allocation_details,
                opp.eligibility,
                opp.access_url,
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
        """Get opportunities with deadlines within the next N days.

        Excludes already-emailed items to prevent duplicates in digest.
        """
        now = datetime.now(timezone.utc).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        rows = self.conn.execute(
            """SELECT * FROM seen_opportunities
            WHERE deadline IS NOT NULL AND deadline >= ? AND deadline <= ?
                  AND status NOT IN ('emailed', 'excluded')
                  AND opportunity_status != 'coming_soon'
            ORDER BY deadline ASC""",
            (now, future),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_coming_soon_opportunities(self) -> list[dict]:
        """Get coming_soon opportunities not yet emailed."""
        rows = self.conn.execute(
            """SELECT * FROM seen_opportunities
            WHERE opportunity_status = 'coming_soon'
                  AND status NOT IN ('emailed', 'excluded')
            ORDER BY source_type, source"""
        ).fetchall()
        return [dict(row) for row in rows]

    def get_rolling_opportunities(self) -> list[dict]:
        """Get open rolling/quarterly deadline opportunities not yet emailed."""
        rows = self.conn.execute(
            """SELECT * FROM seen_opportunities
            WHERE deadline_type IN ('rolling', 'quarterly')
                  AND opportunity_status = 'open'
                  AND status NOT IN ('emailed', 'excluded')
            ORDER BY source_type, source"""
        ).fetchall()
        return [dict(row) for row in rows]

    def refresh_quarterly_deadlines(self) -> int:
        """Refresh quarterly opportunities for the new cycle.

        When a quarterly opportunity's deadline has passed, update its deadline
        to the next quarter end and reset status to 'pending_email' so it
        reappears in the digest as a reminder.

        Returns count of refreshed opportunities.
        """
        now = datetime.now(timezone.utc).isoformat()
        next_q = next_quarter_deadline()

        # Find quarterly opps whose deadline has passed (or was never set)
        rows = self.conn.execute(
            """SELECT composite_id, deadline FROM seen_opportunities
            WHERE deadline_type = 'quarterly'
                  AND opportunity_status = 'open'
                  AND (deadline IS NULL OR deadline < ?)""",
            (now,),
        ).fetchall()

        if not rows:
            return 0

        count = 0
        for row in rows:
            self.conn.execute(
                """UPDATE seen_opportunities
                SET deadline = ?, status = 'pending_email'
                WHERE composite_id = ?""",
                (next_q, row["composite_id"]),
            )
            count += 1

        self.conn.commit()
        if count:
            logger.info(
                f"Refreshed {count} quarterly opportunities: next deadline {next_q}"
            )
        return count

    def get_emailed_opportunities(self) -> list[dict]:
        """Get all opportunities that have been emailed, newest first."""
        rows = self.conn.execute(
            "SELECT * FROM seen_opportunities WHERE status = 'emailed' ORDER BY fetched_at DESC"
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
        """Remove entries older than N days. Returns count deleted.

        Rolling/quarterly opportunities are preserved regardless of age.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cursor = self.conn.execute(
            """DELETE FROM seen_opportunities
            WHERE fetched_at < ?
                  AND deadline_type NOT IN ('rolling', 'quarterly')""",
            (cutoff,),
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

    # --- Source bootstrap operations ---

    def get_unbootstrapped_sources(self, known_sources: list[tuple[str, str]]) -> set[str]:
        """Return source names that have not yet been bootstrapped.

        Registers any new sources with empty bootstrapped_at, then returns
        all source names that still have no bootstrapped_at timestamp.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        for name, stype in known_sources:
            self.conn.execute(
                """INSERT OR IGNORE INTO source_bootstrap
                (source_name, source_type, bootstrapped_at, created_at)
                VALUES (?, ?, '', ?)""",
                (name, stype, now_iso),
            )
        self.conn.commit()
        rows = self.conn.execute(
            "SELECT source_name FROM source_bootstrap WHERE bootstrapped_at = ''"
        ).fetchall()
        return {r["source_name"] for r in rows}

    def mark_source_bootstrapped(self, source_name: str, source_type: str) -> None:
        """Mark a source as bootstrapped after successful first fetch."""
        self.conn.execute(
            """UPDATE source_bootstrap SET bootstrapped_at = ?
            WHERE source_name = ?""",
            (datetime.now(timezone.utc).isoformat(), source_name),
        )
        self.conn.commit()
        logger.info(f"Source '{source_name}' ({source_type}) marked as bootstrapped")

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

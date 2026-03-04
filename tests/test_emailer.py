"""Tests for emailer and state management."""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.emailer import Emailer
from src.models import Opportunity
from src.state import StateDB


class TestStateDB:
    @pytest.fixture
    def db(self, tmp_path: Path) -> StateDB:
        db_path = str(tmp_path / "test.db")
        return StateDB(db_path)

    def test_store_and_dedup(self, db: StateDB):
        opp = Opportunity(
            source="test",
            source_id="123",
            title="Test Opportunity",
            description="Description",
            url="https://example.com",
            relevance_score=0.8,
        )
        assert db.store_opportunity(opp) is True
        assert db.store_opportunity(opp) is False  # Duplicate

    def test_is_seen(self, db: StateDB):
        opp = Opportunity(
            source="test",
            source_id="456",
            title="Another Opp",
            description="Desc",
            url="https://example.com",
        )
        assert db.is_seen("test_456") is False
        db.store_opportunity(opp)
        assert db.is_seen("test_456") is True

    def test_pending_and_emailed(self, db: StateDB):
        opp = Opportunity(
            source="test",
            source_id="789",
            title="Pending Opp",
            description="Desc",
            url="https://example.com",
            source_type="government",
        )
        db.store_opportunity(opp)

        pending = db.get_pending_opportunities()
        assert len(pending) == 1
        assert pending[0]["composite_id"] == "test_789"

        db.mark_emailed(["test_789"])
        pending = db.get_pending_opportunities()
        assert len(pending) == 0

    def test_fetch_history(self, db: StateDB):
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=24)

        assert db.get_last_successful_fetch_end() is None

        db.record_fetch("all", start, now, success=True, count=5)
        last = db.get_last_successful_fetch_end()
        assert last is not None

    def test_upcoming_deadlines(self, db: StateDB):
        future = datetime.now(timezone.utc) + timedelta(days=10)
        opp = Opportunity(
            source="test",
            source_id="dl1",
            title="Deadline Soon",
            description="Desc",
            url="https://example.com",
            deadline=future,
        )
        db.store_opportunity(opp)

        upcoming = db.get_upcoming_deadlines(days=30)
        assert len(upcoming) == 1

    def test_cleanup_old(self, db: StateDB):
        opp = Opportunity(
            source="test",
            source_id="old1",
            title="Old Opp",
            description="Desc",
            url="https://example.com",
        )
        db.store_opportunity(opp)

        # Manually backdate the fetched_at
        old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        db.conn.execute(
            "UPDATE seen_opportunities SET fetched_at = ? WHERE composite_id = ?",
            (old_date, "test_old1"),
        )
        db.conn.commit()

        cleaned = db.cleanup_old(days=90)
        assert cleaned == 1


class TestEmailer:
    def test_compose_html(self, tmp_path: Path):
        # Create a minimal template
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "digest.html").write_text(
            "<html><body>"
            "<h1>{{ date }}</h1>"
            "<p>{{ total_count }} opportunities</p>"
            "{% for src, opps in government_groups.items() %}"
            "{% for opp in opps %}<div>{{ opp.title }}</div>{% endfor %}"
            "{% endfor %}"
            "</body></html>"
        )

        emailer = Emailer(template_dir=str(template_dir))
        html = emailer.compose(
            government_opps=[{"title": "Test Grant", "source": "nsf", "url": "https://example.com"}],
            industry_opps=[],
            upcoming_deadlines=[],
            date_str="March 3, 2026",
        )

        assert "March 3, 2026" in html
        assert "1 opportunities" in html
        assert "Test Grant" in html

    def test_archive_digest(self, tmp_path: Path):
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "digest.html").write_text("<html></html>")

        archive_dir = tmp_path / "archive"
        emailer = Emailer(template_dir=str(template_dir), archive_dir=str(archive_dir))

        path = emailer.archive_digest("<html><body>test</body></html>", "20260303")
        assert path.exists()
        assert path.read_text() == "<html><body>test</body></html>"

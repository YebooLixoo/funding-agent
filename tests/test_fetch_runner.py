"""Tests for web.services.fetch_runner.run_fetch (Task 11).

The runner orchestrates a single fetch run end-to-end. Tests verify the
multi-session boundary contract by patching the remote-I/O helpers
(``_collect_opportunities``, ``_summarize_batch``, ``_filter_opps``) and
asserting the DB-side behavior: opportunity upsert, auto-scoring, and
``fetch_history`` recording.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from src.models import Opportunity as OppDC
from web.models.fetch_history import FetchHistory
from web.models.keyword import UserKeyword
from web.models.opportunity import Opportunity, UserOpportunityScore
from web.services.fetch_runner import run_fetch


def _fake_opp(source: str, source_id: str, source_type: str = "government") -> OppDC:
    return OppDC(
        source=source,
        source_id=source_id,
        title=f"{source}-{source_id}",
        description="ML research opportunity",
        url=f"https://e.com/{source}/{source_id}",
        source_type=source_type,
        relevance_score=0.7,
        summary="auto",
    )


@pytest.mark.asyncio
async def test_run_fetch_writes_opps_scores_and_history(db_session, admin_user, monkeypatch):
    db_session.add(
        UserKeyword(user_id=admin_user.id, keyword="machine learning", category="primary")
    )
    await db_session.commit()

    monkeypatch.setenv("ADMIN_EMAIL", admin_user.email)
    # get_settings() is lru_cached, so set the field explicitly via the cached singleton
    from web.config import get_settings
    get_settings().admin_email = admin_user.email

    fakes = [_fake_opp("nsf", "X1"), _fake_opp("nih", "Y1")]

    with patch(
        "web.services.fetch_runner._collect_opportunities",
        new=AsyncMock(return_value=(fakes, [])),
    ), patch(
        "web.services.fetch_runner._summarize_batch",
        new=AsyncMock(side_effect=lambda opps, model: opps),
    ), patch(
        "web.services.fetch_runner._filter_opps",
        new=AsyncMock(side_effect=lambda opps, **kw: opps),
    ):
        result = await run_fetch(now=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc))

    assert result.stored_count == 2
    assert result.fetch_history_id is not None

    opps = (await db_session.execute(select(Opportunity))).scalars().all()
    assert len(opps) == 2

    scores = (await db_session.execute(select(UserOpportunityScore))).scalars().all()
    assert len(scores) >= 2

    hist = (await db_session.execute(select(FetchHistory))).scalars().all()
    assert len(hist) == 1
    assert hist[0].count == 2 and hist[0].success is True


@pytest.mark.asyncio
async def test_run_fetch_isolates_per_source_errors(db_session, admin_user, monkeypatch):
    db_session.add(UserKeyword(user_id=admin_user.id, keyword="ml", category="primary"))
    await db_session.commit()
    monkeypatch.setenv("ADMIN_EMAIL", admin_user.email)
    from web.config import get_settings
    get_settings().admin_email = admin_user.email

    with patch(
        "web.services.fetch_runner._collect_opportunities",
        new=AsyncMock(return_value=([_fake_opp("nsf", "X1")], ["nih: timeout"])),
    ), patch(
        "web.services.fetch_runner._summarize_batch",
        new=AsyncMock(side_effect=lambda opps, model: opps),
    ), patch(
        "web.services.fetch_runner._filter_opps",
        new=AsyncMock(side_effect=lambda opps, **kw: opps),
    ):
        result = await run_fetch(now=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc))

    assert result.stored_count == 1
    assert result.errors == ["nih: timeout"]
    hist = (await db_session.execute(select(FetchHistory))).scalars().all()
    assert hist[0].error_msg == "nih: timeout"


@pytest.mark.asyncio
async def test_run_fetch_dedup_skips_existing(db_session, admin_user, monkeypatch):
    db_session.add(UserKeyword(user_id=admin_user.id, keyword="ml", category="primary"))
    db_session.add(
        Opportunity(composite_id="nsf_X1", source="nsf", source_id="X1", title="Pre-existing")
    )
    await db_session.commit()
    monkeypatch.setenv("ADMIN_EMAIL", admin_user.email)
    from web.config import get_settings
    get_settings().admin_email = admin_user.email

    with patch(
        "web.services.fetch_runner._collect_opportunities",
        new=AsyncMock(return_value=([_fake_opp("nsf", "X1")], [])),
    ), patch(
        "web.services.fetch_runner._summarize_batch",
        new=AsyncMock(side_effect=lambda opps, model: opps),
    ), patch(
        "web.services.fetch_runner._filter_opps",
        new=AsyncMock(side_effect=lambda opps, **kw: opps),
    ):
        result = await run_fetch(now=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc))

    assert result.stored_count == 0  # dedup matched

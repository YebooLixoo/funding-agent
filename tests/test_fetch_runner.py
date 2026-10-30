"""Tests for web.services.fetch_runner.run_fetch (Task 11).

The runner orchestrates a single fetch run end-to-end. Tests verify the
multi-session boundary contract by patching the remote-I/O helpers
(``_collect_opportunities``, ``_summarize_batch``, ``_filter_opps``) and
asserting the DB-side behavior: opportunity upsert, auto-scoring, and
``fetch_history`` recording.

Bootstrap correctness is NOT directly exercised here — it now requires that
a source actually return >=1 opportunity in the run (Codex feedback on
commit 89bb5e2). See ``_collect_opportunities``'s ``sources_with_results``
set and ``_mark_bootstraps``. Add a dedicated test if bootstrap regressions
are observed in production.
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


@pytest.fixture(autouse=True)
def _isolate_curated(monkeypatch):
    """Neutralize curated synthesis for the orchestration tests below.

    ``run_fetch`` synthesizes ``university.curated`` entries from the real
    conf/sources YAML on every run, which would inflate ``stored_count`` in the
    tests that assert exact counts. These tests exercise fetch/dedup/error/
    history behavior, not curation; ``test_run_fetch_synthesizes_curated_opps``
    re-patches this to cover the curated path.
    """
    monkeypatch.setattr(
        "web.services.fetch_runner._synthesize_curated_opps", lambda cfg: []
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
        new=AsyncMock(return_value=(fakes, [], {"nsf", "nih"})),
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
        new=AsyncMock(
            return_value=([_fake_opp("nsf", "X1")], ["nih: timeout"], {"nsf", "nih"})
        ),
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
        new=AsyncMock(return_value=([_fake_opp("nsf", "X1")], [], {"nsf"})),
    ), patch(
        "web.services.fetch_runner._summarize_batch",
        new=AsyncMock(side_effect=lambda opps, model: opps),
    ), patch(
        "web.services.fetch_runner._filter_opps",
        new=AsyncMock(side_effect=lambda opps, **kw: opps),
    ):
        result = await run_fetch(now=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc))

    assert result.stored_count == 0  # dedup matched


@pytest.mark.asyncio
async def test_run_fetch_synthesizes_curated_opps(db_session, admin_user, monkeypatch):
    """Curated static entries are stored + scored even when the fetch/filter
    pipeline returns nothing (they bypass fetch, filter, and summarizer)."""
    db_session.add(UserKeyword(user_id=admin_user.id, keyword="ml", category="primary"))
    await db_session.commit()
    monkeypatch.setenv("ADMIN_EMAIL", admin_user.email)
    from web.config import get_settings
    get_settings().admin_email = admin_user.email

    curated = _fake_opp("utah_internal", "fsgp", "university")
    # Override the autouse isolation for this test only.
    monkeypatch.setattr(
        "web.services.fetch_runner._synthesize_curated_opps", lambda cfg: [curated]
    )

    with patch(
        "web.services.fetch_runner._collect_opportunities",
        new=AsyncMock(return_value=([], [], set())),
    ), patch(
        "web.services.fetch_runner._summarize_batch",
        new=AsyncMock(side_effect=lambda opps, model: opps),
    ), patch(
        "web.services.fetch_runner._filter_opps",
        new=AsyncMock(side_effect=lambda opps, **kw: opps),
    ):
        result = await run_fetch(now=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc))

    # Curated opp stored despite the pipeline returning zero fetched opps.
    assert result.stored_count == 1
    opps = (await db_session.execute(select(Opportunity))).scalars().all()
    assert [o.composite_id for o in opps] == ["utah_internal_fsgp"]


# --- in-batch dedup ---------------------------------------------------------
# Regression for 2026-10-29: _batch_dedup used a bare >=0.80 title rule and ran
# BEFORE the keyword filter, so an irrelevant near-twin that happened to come
# first shadowed a relevant sibling and both were lost.


def _titled(source: str, source_id: str, title: str, score: float = 0.7) -> OppDC:
    return OppDC(
        source=source,
        source_id=source_id,
        title=title,
        description="d",
        url=f"https://e.com/{source}/{source_id}",
        relevance_score=score,
    )


def test_batch_dedup_keeps_same_source_siblings():
    from web.services.fetch_runner import _batch_dedup

    ctp = "Fiscal Year 2026 Cooperating Technical Partners (CTP) Program - Region"
    lsr = "Landscape Scale Restoration Grant Program for"
    opps = [
        _titled("grants_gov", "1", f"{ctp} 9"),
        _titled("grants_gov", "2", f"{ctp} 8"),
        _titled("grants_gov", "3", f"{lsr} Tribes"),
        _titled("grants_gov", "4", f"{lsr} Non-Federal Lands"),
    ]
    assert [o.source_id for o in _batch_dedup(opps)] == ["1", "2", "3", "4"]


def test_drop_repeated_ids_keeps_first_copy():
    """The main pass and the approaching-deadline pass can return the same record;
    it must be collapsed BEFORE the filter so the LLM doesn't score it twice."""
    from web.services.fetch_runner import _drop_repeated_ids

    first, second = _titled("grants_gov", "1", "Plasma Physics"), _titled("grants_gov", "1", "x")
    opps = [first, _titled("grants_gov", "2", "Other"), second]
    assert _drop_repeated_ids(opps) == [first, opps[1]]


def test_batch_dedup_keeps_highest_scoring_cross_source_twin():
    from web.services.fetch_runner import _batch_dedup

    opps = [
        _titled("nsf", "rss_1", "Plasma Physics", score=0.4),
        _titled("grants_gov", "gg_1", "Plasma Physics", score=0.8),
    ]
    kept = _batch_dedup(opps)
    assert [(o.source, o.relevance_score) for o in kept] == [("grants_gov", 0.8)]


@pytest.mark.asyncio
async def test_run_fetch_filters_before_batch_dedup(db_session, admin_user, monkeypatch):
    db_session.add(UserKeyword(user_id=admin_user.id, keyword="ml", category="primary"))
    await db_session.commit()
    monkeypatch.setenv("ADMIN_EMAIL", admin_user.email)
    from web.config import get_settings
    get_settings().admin_email = admin_user.email

    # Cross-source twins: the first one is irrelevant, the second relevant.
    raw = [
        _titled("nsf", "rss_1", "Plasma Physics"),
        _titled("grants_gov", "gg_1", "Plasma Physics"),
    ]
    with patch(
        "web.services.fetch_runner._collect_opportunities",
        new=AsyncMock(return_value=(raw, [], {"nsf", "grants_gov"})),
    ), patch(
        "web.services.fetch_runner._summarize_batch",
        new=AsyncMock(side_effect=lambda opps, model: opps),
    ), patch(
        "web.services.fetch_runner._filter_opps",
        new=AsyncMock(side_effect=lambda opps, **kw: [o for o in opps if o.source == "grants_gov"]),
    ):
        result = await run_fetch(now=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc))

    assert result.stored_count == 1
    rows = (await db_session.execute(select(Opportunity))).scalars().all()
    assert [r.source for r in rows] == ["grants_gov"]

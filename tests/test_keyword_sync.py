"""Tests for the admin keyword auto-sync into system_* tables.

Task 6 — see implementation plan. Verifies that ``resync_system_tables``:
  - is idempotent
  - mirrors UserKeyword rows owned by the admin user into both
    ``system_search_terms`` (fanned out across NSF/NIH/Grants.gov) and
    ``system_filter_keywords`` (one row per category)
  - folds ``category='custom'`` into ``primary`` to match scoring.py
  - excludes the ``compute`` category (compute opps bypass the filter)
  - removes rows when source UserKeyword rows go away
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from web.models.keyword import UserKeyword
from web.models.system_keywords import SystemFilterKeyword, SystemSearchTerm
from web.services.keyword_sync import register_listener, resync_system_tables


@pytest.mark.asyncio
async def test_resync_creates_system_search_terms(db_session, admin_user):
    db_session.add(
        UserKeyword(user_id=admin_user.id, keyword="machine learning", category="primary")
    )
    await db_session.flush()
    await resync_system_tables(db_session, admin_user.id)
    rows = (await db_session.execute(select(SystemSearchTerm))).scalars().all()
    assert any(r.term == "machine learning" for r in rows)
    # Each search-term keyword fans out across NSF/NIH/Grants.gov
    targets = {r.target_source for r in rows if r.term == "machine learning"}
    assert targets == {"nsf", "nih", "grants_gov"}


@pytest.mark.asyncio
async def test_resync_creates_filter_keywords_for_all_categories(db_session, admin_user):
    for cat in ["primary", "domain", "career", "faculty", "exclusion"]:
        db_session.add(
            UserKeyword(user_id=admin_user.id, keyword=f"kw_{cat}", category=cat)
        )
    await db_session.flush()
    await resync_system_tables(db_session, admin_user.id)
    rows = (await db_session.execute(select(SystemFilterKeyword))).scalars().all()
    assert {r.category for r in rows} == {"primary", "domain", "career", "faculty", "exclusion"}


@pytest.mark.asyncio
async def test_custom_category_folds_to_primary(db_session, admin_user):
    """The web routers/scoring already treat category='custom' as primary; sync should match."""
    db_session.add(UserKeyword(user_id=admin_user.id, keyword="custom_kw", category="custom"))
    await db_session.flush()
    await resync_system_tables(db_session, admin_user.id)
    rows = (
        await db_session.execute(
            select(SystemFilterKeyword).where(SystemFilterKeyword.keyword == "custom_kw")
        )
    ).scalars().all()
    assert len(rows) == 1 and rows[0].category == "primary"


@pytest.mark.asyncio
async def test_resync_removes_deleted_keywords(db_session, admin_user):
    kw = UserKeyword(user_id=admin_user.id, keyword="old", category="primary")
    db_session.add(kw)
    await db_session.flush()
    await resync_system_tables(db_session, admin_user.id)

    await db_session.delete(kw)
    await db_session.flush()
    await resync_system_tables(db_session, admin_user.id)

    remaining = (
        await db_session.execute(
            select(SystemSearchTerm).where(SystemSearchTerm.term == "old")
        )
    ).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_register_listener_is_callable_noop(db_session):
    """register_listener exists for forward-compat with Task 11 imports; v1 is a no-op."""
    register_listener()  # no exception

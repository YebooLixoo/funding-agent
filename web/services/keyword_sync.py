"""Mirror admin ``UserKeyword`` rows into the system_* tables.

Design (Task 6):
    Rather than register a sync ``after_flush`` listener (the pattern hinted at
    in the original plan), we expose an explicit, idempotent async helper
    ``resync_system_tables`` that the keyword router and the fetch_runner call
    directly. The flush-time listener is omitted because:

    1. Our session is ``AsyncSession``; ``after_flush`` fires sync against the
       underlying sync session, so issuing additional INSERT/DELETE from inside
       the flush hook has subtle ordering/re-entrancy issues with
       ``expire_on_commit=False`` and the test fixtures.
    2. Explicit calls are easier to reason about and easier to test.
    3. Every code path that mutates admin keywords goes through either the
       router (per-mutation resync) or the fetch_runner (idempotent backstop
       at the start of each fetch).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from web.models.keyword import UserKeyword
from web.models.system_keywords import SystemFilterKeyword, SystemSearchTerm

logger = logging.getLogger(__name__)

# Categories that contribute to API search terms (NSF/NIH/Grants.gov queries).
_SEARCH_TERM_CATEGORIES = {"primary", "domain", "career", "faculty"}

# Categories that contribute to the fetch-time relevance filter.
# Note: ``compute`` is intentionally absent — compute opportunities bypass the
# keyword filter (see src/weekly_fetch.py:395). ``custom`` folds to ``primary``
# to match scoring.py:77 behavior.
_FILTER_KEYWORD_CATEGORIES = {"primary", "domain", "career", "faculty", "exclusion"}

# Each search keyword is fanned out across these API targets.
_SOURCE_TARGETS = ("nsf", "nih", "grants_gov")


def _normalize_category(category: str) -> str:
    """Match scoring.py:77 — ``custom`` is treated as ``primary``."""
    return "primary" if category == "custom" else category


async def resync_system_tables(db: AsyncSession, admin_user_id: uuid.UUID) -> None:
    """Idempotent: rebuild system_* tables from admin's active UserKeyword rows.

    Safe to call repeatedly. Adds rows that should exist; deletes rows that no
    longer should. Only touches rows in system_* tables that were sourced from
    the given admin user.
    """
    user_keywords = (
        await db.execute(
            select(UserKeyword).where(
                UserKeyword.user_id == admin_user_id,
                UserKeyword.is_active.is_(True),
            )
        )
    ).scalars().all()

    # ---------- SystemFilterKeyword ----------
    desired_filter = {
        (kw.keyword.lower(), _normalize_category(kw.category))
        for kw in user_keywords
        if _normalize_category(kw.category) in _FILTER_KEYWORD_CATEGORIES
    }

    existing_filter = (
        await db.execute(
            select(SystemFilterKeyword).where(
                SystemFilterKeyword.source_user_id == admin_user_id
            )
        )
    ).scalars().all()
    existing_filter_keys = {(r.keyword, r.category) for r in existing_filter}

    to_add_filter = desired_filter - existing_filter_keys
    to_remove_filter = existing_filter_keys - desired_filter

    for keyword, category in to_add_filter:
        db.add(
            SystemFilterKeyword(
                keyword=keyword,
                category=category,
                source_user_id=admin_user_id,
                is_active=True,
            )
        )

    for keyword, category in to_remove_filter:
        await db.execute(
            delete(SystemFilterKeyword).where(
                SystemFilterKeyword.source_user_id == admin_user_id,
                SystemFilterKeyword.keyword == keyword,
                SystemFilterKeyword.category == category,
            )
        )

    # ---------- SystemSearchTerm (fan out over targets) ----------
    desired_terms = {
        kw.keyword.lower()
        for kw in user_keywords
        if _normalize_category(kw.category) in _SEARCH_TERM_CATEGORIES
    }
    desired_st = {(t, src) for t in desired_terms for src in _SOURCE_TARGETS}

    existing_st = (
        await db.execute(
            select(SystemSearchTerm).where(
                SystemSearchTerm.source_user_id == admin_user_id
            )
        )
    ).scalars().all()
    existing_st_keys = {(r.term, r.target_source) for r in existing_st}

    to_add_st = desired_st - existing_st_keys
    to_remove_st = existing_st_keys - desired_st

    for term, src in to_add_st:
        db.add(
            SystemSearchTerm(
                term=term,
                target_source=src,
                source_user_id=admin_user_id,
                is_active=True,
            )
        )

    for term, src in to_remove_st:
        await db.execute(
            delete(SystemSearchTerm).where(
                SystemSearchTerm.source_user_id == admin_user_id,
                SystemSearchTerm.term == term,
                SystemSearchTerm.target_source == src,
            )
        )

    await db.flush()


def register_listener() -> None:
    """Forward-compat no-op stub.

    A future enhancement could install an ``after_flush`` hook that calls
    :func:`resync_system_tables` automatically. v1 instead relies on explicit
    calls from:
      - ``web/routers/keywords.py`` — after each admin keyword mutation
      - ``web/services/fetch_runner.py`` — idempotent backstop at fetch start
    Both paths cover all current code that mutates admin keywords.
    """
    return

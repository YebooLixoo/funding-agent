"""Async upsert helper for ``Opportunity`` rows.

Ports the dedup logic from ``src/state.py:StateDB.store_opportunity`` to a
SQLAlchemy async helper. Three dedup paths (composite_id, URL,
title-similarity >= 0.80) precede the actual insert.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.models.opportunity import Opportunity as OppRow

if TYPE_CHECKING:
    from src.models import Opportunity as OppDC


_TITLE_THRESHOLD = 0.80


def _normalize(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", title.lower().strip()))


async def upsert_opportunity(db: AsyncSession, opp: "OppDC") -> tuple[OppRow, bool]:
    """Insert ``opp`` if not duplicate. Returns ``(row, was_new)``.

    Dedup order matches ``StateDB.store_opportunity``:
      1. composite_id ("{source}_{source_id}")
      2. exact URL match
      3. title similarity >= 0.80 (SequenceMatcher on normalized titles)
    """
    composite_id = f"{opp.source}_{opp.source_id}"

    # Dedup lookups use ``.scalars().first()`` (not ``.scalar_one_or_none()``)
    # deliberately. Dedup asks "is this opp already stored?", for which
    # one-OR-MORE matches means "yes" — asserting *exactly* one made the whole
    # fetch crash with ``MultipleResultsFound`` when two legitimately-distinct
    # rows shared a value. ``url`` is a NON-unique column (e.g. two NVIDIA grant
    # tracks share one landing-page URL), so >1 match is expected, not an error.
    # ``order_by(id).limit(1)`` keeps the chosen survivor stable across runs and
    # pushes the limit into SQL. ``composite_id`` has a UNIQUE index so it can
    # match at most one row today, but uses the same tolerant pattern so a future
    # duplicate degrades to a dedup instead of crashing the run.

    # 1. dedup by composite_id
    existing = (
        await db.execute(
            select(OppRow)
            .where(OppRow.composite_id == composite_id)
            .order_by(OppRow.id)
            .limit(1)
        )
    ).scalars().first()
    if existing:
        return existing, False

    # 2. dedup by URL (non-unique column — may legitimately match multiple rows)
    if opp.url:
        existing = (
            await db.execute(
                select(OppRow)
                .where(OppRow.url == opp.url)
                .order_by(OppRow.id)
                .limit(1)
            )
        ).scalars().first()
        if existing:
            return existing, False

    # 3. dedup by title-similarity
    norm = _normalize(opp.title)
    candidates = (await db.execute(select(OppRow.id, OppRow.title))).all()
    for row_id, row_title in candidates:
        if SequenceMatcher(None, norm, _normalize(row_title or "")).ratio() >= _TITLE_THRESHOLD:
            existing = await db.get(OppRow, row_id)
            return existing, False

    # 4. insert
    row = OppRow(
        composite_id=composite_id,
        source=opp.source,
        source_id=opp.source_id,
        title=opp.title,
        description=opp.description,
        url=opp.url,
        source_type=opp.source_type,
        deadline=opp.deadline.isoformat() if opp.deadline else None,
        posted_date=opp.posted_date.isoformat() if opp.posted_date else None,
        funding_amount=opp.funding_amount,
        keywords=opp.keywords,
        summary=opp.summary,
        opportunity_status=opp.opportunity_status,
        deadline_type=opp.deadline_type,
        resource_type=opp.resource_type,
        resource_provider=opp.resource_provider,
        resource_scale=opp.resource_scale,
        allocation_details=opp.allocation_details,
        eligibility=opp.eligibility,
        access_url=opp.access_url,
        agency=getattr(opp, "agency", None),
    )
    db.add(row)
    await db.flush()
    return row, True

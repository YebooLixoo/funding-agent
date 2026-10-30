"""Async upsert helper for ``Opportunity`` rows.

Ports the dedup logic from ``src/state.py:StateDB.store_opportunity`` to a
SQLAlchemy async helper. Three dedup paths (composite_id, URL, title match —
see ``titles_match``) precede the actual insert.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import title_derived_source_id
from web.models.opportunity import Opportunity as OppRow

if TYPE_CHECKING:
    from src.models import Opportunity as OppDC


_TITLE_THRESHOLD = 0.80
_DIGITS = re.compile(r"\d+")


def _normalize(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", title.lower().strip()))


def _day(deadline) -> str | None:
    """``YYYY-MM-DD`` of a deadline given as a datetime/date or ISO string."""
    return str(deadline)[:10] if deadline else None


def _numbers(title: str) -> set[int]:
    """Integers in the raw title (before punctuation stripping glues '2024-2026')."""
    return {int(n) for n in _DIGITS.findall(title)}


def _has_upstream_id(rec) -> bool:
    """False for scraped items whose id is just a hash of their own title."""
    return rec.source_id != title_derived_source_id(rec.source, rec.title or "")


def titles_match(a, b) -> bool:
    """Do ``a`` and ``b`` look like the same opportunity, judging by title?

    Takes anything with ``source``/``source_id``/``title``/``deadline``
    (dataclass or DB row). Templated titles ("Fiscal Year 2026 ... - Region 9",
    "... Cooperative Ecosystem Studies Unit") are highly similar across distinct
    opportunities, so similarity is overruled by anything that tells two
    records apart:

    - both deadlines known and different -> a new cycle, not a duplicate;
    - same source with upstream ids (grants.gov, curated YAML) -> the ids are
      authoritative (distinct ids reach here), so only an exact re-post
      (identical title AND known deadline) is a duplicate;
    - otherwise (across sources, or scraper ids that merely hash the title) ->
      numbers in the titles (fiscal year, region, cycle) must agree, then
      SequenceMatcher >= ``_TITLE_THRESHOLD``.
    """
    day_a, day_b = _day(a.deadline), _day(b.deadline)
    if day_a and day_b and day_a != day_b:
        return False
    norm_a, norm_b = _normalize(a.title or ""), _normalize(b.title or "")
    if a.source == b.source and _has_upstream_id(a) and _has_upstream_id(b):
        return norm_a == norm_b and day_a is not None and day_a == day_b
    if _numbers(a.title or "") != _numbers(b.title or ""):
        return False
    return SequenceMatcher(None, norm_a, norm_b).ratio() >= _TITLE_THRESHOLD


async def upsert_opportunity(db: AsyncSession, opp: "OppDC") -> tuple[OppRow, bool]:
    """Insert ``opp`` if not duplicate. Returns ``(row, was_new)``.

    Dedup order matches ``StateDB.store_opportunity``:
      1. composite_id ("{source}_{source_id}")
      2. exact URL match
      3. title match against any stored row (``titles_match``)
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

    # 3. dedup by title match
    candidates = (
        await db.execute(
            select(OppRow.id, OppRow.source, OppRow.source_id, OppRow.title, OppRow.deadline)
        )
    ).all()
    for cand in candidates:
        if titles_match(opp, cand):
            existing = await db.get(OppRow, cand.id)
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

"""Per-user fetcher service.

Wraps the internal fetcher modules to perform per-user fetches
based on their keyword profile and source configuration.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.models.fetch_config import UserFetchConfig
from web.models.keyword import UserKeyword
from web.models.opportunity import Opportunity

logger = logging.getLogger(__name__)


async def get_user_search_terms(db: AsyncSession, user_id) -> list[str]:
    """Build search terms from user's active keywords."""
    result = await db.execute(
        select(UserKeyword).where(
            UserKeyword.user_id == user_id,
            UserKeyword.is_active.is_(True),
            UserKeyword.category.in_(["primary", "domain", "custom"]),
        )
    )
    keywords = result.scalars().all()
    return [kw.keyword for kw in keywords]


async def store_fetched_opportunity(
    db: AsyncSession,
    source: str,
    source_id: str,
    title: str,
    description: str,
    url: str,
    source_type: str = "government",
    deadline: str | None = None,
    posted_date: str | None = None,
    funding_amount: str | None = None,
    keywords: list[str] | None = None,
    summary: str | None = None,
    user_id=None,
) -> Opportunity | None:
    """Store a fetched opportunity, skipping duplicates by composite_id."""
    composite_id = f"{source}_{source_id}"

    existing = await db.execute(
        select(Opportunity).where(Opportunity.composite_id == composite_id)
    )
    if existing.scalar_one_or_none():
        return None  # Already exists

    opp = Opportunity(
        composite_id=composite_id,
        source=source,
        source_id=source_id,
        title=title,
        description=description,
        url=url,
        source_type=source_type,
        deadline=deadline,
        posted_date=posted_date,
        funding_amount=funding_amount,
        keywords=keywords,
        summary=summary,
        fetched_for_user_id=user_id,
    )
    db.add(opp)
    await db.flush()
    return opp

"""Per-user scoring service that wraps the internal KeywordFilter."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.models.keyword import UserKeyword
from web.models.opportunity import Opportunity, UserOpportunityScore

# Import the proven internal scoring algorithm and data model
from src.filter.keyword_filter import FilterConfig, KeywordFilter
from src.models import Opportunity as InternalOpportunity


async def build_filter_config(db: AsyncSession, user_id) -> FilterConfig:
    """Build a FilterConfig from a user's keywords in the platform DB."""
    result = await db.execute(
        select(UserKeyword).where(
            UserKeyword.user_id == user_id,
            UserKeyword.is_active.is_(True),
        )
    )
    keywords = result.scalars().all()

    primary = []
    domain = []
    career = []
    faculty = []
    exclusions = []

    for kw in keywords:
        if kw.category == "primary":
            primary.append(kw.keyword)
        elif kw.category == "domain":
            domain.append(kw.keyword)
        elif kw.category == "career":
            career.append(kw.keyword)
        elif kw.category == "faculty":
            faculty.append(kw.keyword)
        elif kw.category == "exclusion":
            exclusions.append(kw.keyword)
        elif kw.category == "custom":
            # Custom keywords contribute to primary by default
            primary.append(kw.keyword)

    return FilterConfig(
        primary_keywords=primary,
        domain_keywords=domain,
        career_keywords=career,
        faculty_keywords=faculty,
        exclusions=exclusions,
    )


def _to_internal_opp(opp: Opportunity) -> InternalOpportunity:
    """Convert platform ORM Opportunity to internal dataclass for scoring."""
    return InternalOpportunity(
        source=opp.source,
        source_id=opp.source_id,
        title=opp.title,
        description=opp.description or "",
        url=opp.url or "",
        source_type=opp.source_type or "government",
        summary=opp.summary or "",
    )


async def score_opportunity_for_user(
    db: AsyncSession, user_id, opportunity: Opportunity
) -> UserOpportunityScore:
    """Score a single opportunity for a user using their keyword profile."""
    config = await build_filter_config(db, user_id)
    kf = KeywordFilter(config)

    internal_opp = _to_internal_opp(opportunity)
    score = kf.score(internal_opp)
    matched = kf.extract_matching_keywords(internal_opp)

    # Upsert the score
    result = await db.execute(
        select(UserOpportunityScore).where(
            UserOpportunityScore.user_id == user_id,
            UserOpportunityScore.opportunity_id == opportunity.id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.relevance_score = score
        existing.matched_keywords = matched
        return existing

    user_score = UserOpportunityScore(
        user_id=user_id,
        opportunity_id=opportunity.id,
        relevance_score=score,
        matched_keywords=matched,
    )
    db.add(user_score)
    await db.flush()
    return user_score


async def score_all_opportunities_for_user(db: AsyncSession, user_id) -> int:
    """Score all opportunities for a user. Returns count of scored items."""
    config = await build_filter_config(db, user_id)
    kf = KeywordFilter(config)

    result = await db.execute(select(Opportunity))
    opportunities = result.scalars().all()

    count = 0
    for opp in opportunities:
        internal_opp = _to_internal_opp(opp)
        score = kf.score(internal_opp)
        matched = kf.extract_matching_keywords(internal_opp)

        score_result = await db.execute(
            select(UserOpportunityScore).where(
                UserOpportunityScore.user_id == user_id,
                UserOpportunityScore.opportunity_id == opp.id,
            )
        )
        existing = score_result.scalar_one_or_none()
        if existing:
            existing.relevance_score = score
            existing.matched_keywords = matched
        else:
            db.add(UserOpportunityScore(
                user_id=user_id,
                opportunity_id=opp.id,
                relevance_score=score,
                matched_keywords=matched,
            ))
        count += 1

    await db.flush()
    return count

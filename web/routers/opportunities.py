from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from web.database import get_db
from web.dependencies import get_current_user
from web.models.opportunity import Opportunity, UserOpportunityScore
from web.models.user import User
from web.schemas.opportunity import OpportunityListResponse, OpportunityResponse

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _opp_to_response(opp: Opportunity, score: UserOpportunityScore | None = None) -> OpportunityResponse:
    data = {
        "id": opp.id,
        "composite_id": opp.composite_id,
        "source": opp.source,
        "source_id": opp.source_id,
        "title": opp.title,
        "description": opp.description,
        "url": opp.url,
        "source_type": opp.source_type,
        "deadline": opp.deadline,
        "posted_date": opp.posted_date,
        "funding_amount": opp.funding_amount,
        "keywords": opp.keywords,
        "summary": opp.summary,
        "opportunity_status": opp.opportunity_status,
        "deadline_type": getattr(opp, 'deadline_type', 'fixed'),
        "resource_type": getattr(opp, 'resource_type', None),
        "resource_provider": getattr(opp, 'resource_provider', None),
        "resource_scale": getattr(opp, 'resource_scale', None),
        "allocation_details": getattr(opp, 'allocation_details', None),
        "eligibility": getattr(opp, 'eligibility', None),
        "access_url": getattr(opp, 'access_url', None),
        "fetched_at": opp.fetched_at,
    }
    if score:
        data["relevance_score"] = score.relevance_score
        data["keyword_score"] = score.keyword_score
        data["profile_score"] = score.profile_score
        data["behavior_score"] = score.behavior_score
        data["urgency_score"] = score.urgency_score
        data["matched_keywords"] = score.matched_keywords
        data["is_bookmarked"] = score.is_bookmarked or False
        data["is_dismissed"] = score.is_dismissed or False
    return OpportunityResponse(**data)


@router.get("", response_model=OpportunityListResponse)
async def list_opportunities(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    opportunity_status: Optional[str] = Query(None, pattern="^(open|coming_soon|closed)$"),
    search: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=1),
    sort_by: str = Query("fetched_at", pattern="^(fetched_at|deadline|relevance_score)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Base query
    query = select(Opportunity)
    count_query = select(func.count(Opportunity.id))

    # Filters
    if source:
        query = query.where(Opportunity.source == source)
        count_query = count_query.where(Opportunity.source == source)
    if source_type:
        query = query.where(Opportunity.source_type == source_type)
        count_query = count_query.where(Opportunity.source_type == source_type)
    if opportunity_status:
        query = query.where(Opportunity.opportunity_status == opportunity_status)
        count_query = count_query.where(Opportunity.opportunity_status == opportunity_status)
    if search:
        pattern = f"%{search}%"
        search_filter = or_(
            Opportunity.title.ilike(pattern),
            Opportunity.description.ilike(pattern),
            Opportunity.summary.ilike(pattern),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    # Join with user scores when needed for sorting or min_score filtering
    needs_score_join = sort_by == "relevance_score" or min_score is not None
    if needs_score_join:
        query = query.outerjoin(
            UserOpportunityScore,
            (UserOpportunityScore.opportunity_id == Opportunity.id)
            & (UserOpportunityScore.user_id == current_user.id),
        )
        count_query = count_query.outerjoin(
            UserOpportunityScore,
            (UserOpportunityScore.opportunity_id == Opportunity.id)
            & (UserOpportunityScore.user_id == current_user.id),
        )
        score_col = func.coalesce(UserOpportunityScore.relevance_score, 0.0)

    # Apply min_score filter in SQL so pagination counts are correct
    if min_score is not None:
        query = query.where(score_col >= min_score)
        count_query = count_query.where(score_col >= min_score)

    # Sorting
    if sort_by == "relevance_score":
        if sort_order == "desc":
            query = query.order_by(score_col.desc())
        else:
            query = query.order_by(score_col.asc())
    else:
        order_col = Opportunity.fetched_at if sort_by == "fetched_at" else Opportunity.deadline
        if sort_order == "desc":
            query = query.order_by(order_col.desc())
        else:
            query = query.order_by(order_col.asc())

    # Count
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    opportunities = result.scalars().all()

    # Get user scores for these opportunities
    if opportunities:
        opp_ids = [o.id for o in opportunities]
        scores_result = await db.execute(
            select(UserOpportunityScore).where(
                UserOpportunityScore.user_id == current_user.id,
                UserOpportunityScore.opportunity_id.in_(opp_ids),
            )
        )
        scores = {s.opportunity_id: s for s in scores_result.scalars().all()}
    else:
        scores = {}

    items = [_opp_to_response(opp, scores.get(opp.id)) for opp in opportunities]

    total_pages = (total + page_size - 1) // page_size

    return OpportunityListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# NOTE: /bookmarks/list MUST be defined before /{opportunity_id} to avoid route shadowing
@router.get("/bookmarks/list", response_model=list[OpportunityResponse])
async def list_bookmarks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Opportunity, UserOpportunityScore)
        .join(
            UserOpportunityScore,
            UserOpportunityScore.opportunity_id == Opportunity.id,
        )
        .where(
            UserOpportunityScore.user_id == current_user.id,
            UserOpportunityScore.is_bookmarked.is_(True),
        )
        .order_by(UserOpportunityScore.scored_at.desc())
    )
    rows = result.all()
    return [_opp_to_response(opp, score) for opp, score in rows]


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(
    opportunity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    opp = result.scalar_one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    score_result = await db.execute(
        select(UserOpportunityScore).where(
            UserOpportunityScore.user_id == current_user.id,
            UserOpportunityScore.opportunity_id == opportunity_id,
        )
    )
    score = score_result.scalar_one_or_none()

    # Track view interaction for recommendation algorithm
    if score:
        score.view_count = (score.view_count or 0) + 1
        score.clicked_at = datetime.now(timezone.utc)
    else:
        score = UserOpportunityScore(
            user_id=current_user.id,
            opportunity_id=opportunity_id,
            view_count=1,
            clicked_at=datetime.now(timezone.utc),
        )
        db.add(score)

    return _opp_to_response(opp, score)


@router.post("/{opportunity_id}/bookmark", status_code=status.HTTP_200_OK)
async def bookmark_opportunity(
    opportunity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify opportunity exists
    result = await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Opportunity not found")

    score_result = await db.execute(
        select(UserOpportunityScore).where(
            UserOpportunityScore.user_id == current_user.id,
            UserOpportunityScore.opportunity_id == opportunity_id,
        )
    )
    score = score_result.scalar_one_or_none()
    if score:
        score.is_bookmarked = True
    else:
        score = UserOpportunityScore(
            user_id=current_user.id,
            opportunity_id=opportunity_id,
            is_bookmarked=True,
        )
        db.add(score)
    return {"status": "bookmarked"}


@router.delete("/{opportunity_id}/bookmark", status_code=status.HTTP_200_OK)
async def unbookmark_opportunity(
    opportunity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    score_result = await db.execute(
        select(UserOpportunityScore).where(
            UserOpportunityScore.user_id == current_user.id,
            UserOpportunityScore.opportunity_id == opportunity_id,
        )
    )
    score = score_result.scalar_one_or_none()
    if score:
        score.is_bookmarked = False
    return {"status": "unbookmarked"}


@router.post("/{opportunity_id}/dismiss", status_code=status.HTTP_200_OK)
async def dismiss_opportunity(
    opportunity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Opportunity not found")

    score_result = await db.execute(
        select(UserOpportunityScore).where(
            UserOpportunityScore.user_id == current_user.id,
            UserOpportunityScore.opportunity_id == opportunity_id,
        )
    )
    score = score_result.scalar_one_or_none()
    if score:
        score.is_dismissed = True
    else:
        score = UserOpportunityScore(
            user_id=current_user.id,
            opportunity_id=opportunity_id,
            is_dismissed=True,
        )
        db.add(score)
    return {"status": "dismissed"}

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.database import get_db
from web.dependencies import get_current_user
from web.models.opportunity import Opportunity, UserOpportunityScore
from web.models.user import User
from web.services.scoring import score_all_opportunities_for_user, score_opportunity_for_user

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.post("/rescore")
async def rescore_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await score_all_opportunities_for_user(db, current_user.id)
    return {"status": "ok", "scored_count": count}


@router.get("/explain/{opportunity_id}")
async def explain_score(
    opportunity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the score breakdown for a single opportunity."""
    result = await db.execute(
        select(Opportunity).where(Opportunity.id == opportunity_id)
    )
    opp = result.scalar_one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    # Score (or re-score) the opportunity
    user_score = await score_opportunity_for_user(
        db, current_user.id, opp, user=current_user,
    )

    return {
        "opportunity_id": str(opportunity_id),
        "relevance_score": user_score.relevance_score,
        "breakdown": {
            "keyword": {"score": user_score.keyword_score, "weight": 0.40},
            "profile": {"score": user_score.profile_score, "weight": 0.30},
            "behavior": {"score": user_score.behavior_score, "weight": 0.20},
            "urgency": {"score": user_score.urgency_score, "weight": 0.10},
        },
        "matched_keywords": user_score.matched_keywords or [],
    }

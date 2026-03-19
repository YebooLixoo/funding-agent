from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from web.database import get_db
from web.dependencies import get_current_user
from web.models.user import User
from web.services.scoring import score_all_opportunities_for_user

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.post("/rescore")
async def rescore_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await score_all_opportunities_for_user(db, current_user.id)
    return {"status": "ok", "scored_count": count}

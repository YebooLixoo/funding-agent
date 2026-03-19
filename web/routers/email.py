from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.database import get_db
from web.dependencies import get_current_user
from web.models.email_pref import UserEmailHistory, UserEmailPref
from web.models.user import User
from web.schemas.email_pref import EmailHistoryResponse, EmailPrefResponse, EmailPrefUpdate

router = APIRouter(prefix="/email", tags=["email"])


async def _get_or_create_pref(db: AsyncSession, user: User) -> UserEmailPref:
    result = await db.execute(
        select(UserEmailPref).where(UserEmailPref.user_id == user.id)
    )
    pref = result.scalar_one_or_none()
    if not pref:
        pref = UserEmailPref(user_id=user.id)
        db.add(pref)
        await db.flush()
    return pref


@router.get("/preferences", response_model=EmailPrefResponse)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_or_create_pref(db, current_user)


@router.put("/preferences", response_model=EmailPrefResponse)
async def update_preferences(
    body: EmailPrefUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pref = await _get_or_create_pref(db, current_user)
    update_data = body.model_dump(exclude_unset=True)

    if "frequency" in update_data:
        if update_data["frequency"] not in ("daily", "weekly", "biweekly"):
            raise HTTPException(status_code=400, detail="frequency must be daily, weekly, or biweekly")

    if "day_of_week" in update_data:
        if not 0 <= update_data["day_of_week"] <= 6:
            raise HTTPException(status_code=400, detail="day_of_week must be 0-6")

    for field, value in update_data.items():
        setattr(pref, field, value)
    await db.flush()
    return pref


@router.post("/unsubscribe")
async def unsubscribe(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pref = await _get_or_create_pref(db, current_user)
    pref.is_subscribed = False
    await db.flush()
    return {"status": "unsubscribed"}


@router.get("/history", response_model=list[EmailHistoryResponse])
async def email_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserEmailHistory)
        .where(UserEmailHistory.user_id == current_user.id)
        .order_by(UserEmailHistory.sent_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.post("/send-test")
async def send_test_email(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a test email to the current user (placeholder — requires email service)."""
    # In production, this would call the email scheduler service
    # For now, record the attempt
    history = UserEmailHistory(
        user_id=current_user.id,
        opportunity_count=0,
        success=True,
        error_msg="Test email (placeholder — email service not yet configured)",
    )
    db.add(history)
    await db.flush()
    return {"status": "test_sent", "message": "Test email queued (placeholder)"}

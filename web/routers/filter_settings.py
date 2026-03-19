from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.database import get_db
from web.dependencies import get_current_user
from web.models.filter_settings import UserFilterSettings
from web.models.user import User
from web.schemas.filter_settings import FilterSettingsResponse, FilterSettingsUpdate

router = APIRouter(prefix="/filter-settings", tags=["filter-settings"])


async def _get_or_create(db: AsyncSession, user: User) -> UserFilterSettings:
    result = await db.execute(
        select(UserFilterSettings).where(UserFilterSettings.user_id == user.id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserFilterSettings(user_id=user.id)
        db.add(settings)
        await db.flush()
    return settings


@router.get("", response_model=FilterSettingsResponse)
async def get_filter_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_or_create(db, current_user)


@router.put("", response_model=FilterSettingsResponse)
async def update_filter_settings(
    body: FilterSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = await _get_or_create(db, current_user)
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)
    await db.flush()
    return settings

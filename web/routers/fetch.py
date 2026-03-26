from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.database import get_db
from web.dependencies import get_current_user
from web.models.fetch_config import UserFetchConfig
from web.models.user import User
from web.schemas.fetch_config import FetchConfigResponse, FetchConfigUpdate
from web.services.university_fetcher import get_university_sources, list_supported_institutions

router = APIRouter(prefix="/fetch", tags=["fetch"])

# Default available sources
AVAILABLE_SOURCES = ["nsf", "nih", "grants_gov", "web_sources_gov", "web_sources_industry", "university"]


async def _get_or_create_config(db: AsyncSession, user: User) -> UserFetchConfig:
    result = await db.execute(
        select(UserFetchConfig).where(UserFetchConfig.user_id == user.id)
    )
    config = result.scalar_one_or_none()
    if not config:
        config = UserFetchConfig(
            user_id=user.id,
            sources_enabled={s: True for s in AVAILABLE_SOURCES},
        )
        db.add(config)
        await db.flush()
    return config


@router.get("/config", response_model=FetchConfigResponse)
async def get_fetch_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_or_create_config(db, current_user)


@router.put("/config", response_model=FetchConfigResponse)
async def update_fetch_config(
    body: FetchConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = await _get_or_create_config(db, current_user)
    update_data = body.model_dump(exclude_unset=True)

    if "fetch_frequency" in update_data:
        if update_data["fetch_frequency"] not in ("daily", "weekly", "biweekly"):
            raise HTTPException(status_code=400, detail="fetch_frequency must be daily, weekly, or biweekly")

    for field, value in update_data.items():
        setattr(config, field, value)
    await db.flush()
    return config


@router.post("/trigger")
async def trigger_fetch(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a fetch with user's keywords (placeholder)."""
    config = await _get_or_create_config(db, current_user)
    config.last_fetched_at = datetime.now(timezone.utc)
    await db.flush()
    return {
        "status": "triggered",
        "message": "Fetch triggered (placeholder — background fetch service not yet configured)",
    }


@router.get("/university-sources")
async def get_user_university_sources(
    current_user: User = Depends(get_current_user),
):
    """Get university funding sources based on the user's institution."""
    sources = get_university_sources(current_user.institution)
    return {
        "institution": current_user.institution,
        "sources": sources,
        "supported_institutions": list_supported_institutions(),
    }


@router.get("/status")
async def fetch_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = await _get_or_create_config(db, current_user)
    return {
        "last_fetched_at": config.last_fetched_at.isoformat() if config.last_fetched_at else None,
        "fetch_frequency": config.fetch_frequency,
        "sources_enabled": config.sources_enabled,
    }

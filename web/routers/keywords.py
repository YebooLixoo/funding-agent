from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.database import get_db
from web.dependencies import get_current_user
from web.models.keyword import UserKeyword
from web.models.user import User
from web.schemas.keyword import (
    KeywordBulkCreate,
    KeywordCreate,
    KeywordResponse,
    KeywordsByCategory,
    KeywordUpdate,
)
from web.services.keyword_sync import resync_system_tables

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/keywords", tags=["keywords"])

VALID_CATEGORIES = {"primary", "domain", "career", "faculty", "exclusion", "custom"}


async def _maybe_sync_admin(db: AsyncSession, user: User) -> None:
    """If ``user`` is admin, mirror their keywords into system_* tables.

    Failures are logged but never raised — a sync issue must not break the
    user's keyword edit. The fetch_runner backstop will catch up later.
    """
    if not user.is_admin:
        return
    try:
        await resync_system_tables(db, user.id)
    except Exception:  # noqa: BLE001 — non-fatal, fetch_runner is the backstop
        logger.exception("admin keyword sync failed (non-fatal)")


@router.get("", response_model=KeywordsByCategory)
async def list_keywords(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserKeyword)
        .where(UserKeyword.user_id == current_user.id)
        .order_by(UserKeyword.category, UserKeyword.keyword)
    )
    keywords = result.scalars().all()

    grouped = KeywordsByCategory()
    for kw in keywords:
        cat_list = getattr(grouped, kw.category, None)
        if cat_list is not None:
            cat_list.append(KeywordResponse.model_validate(kw))
    return grouped


@router.post("", response_model=KeywordResponse, status_code=status.HTTP_201_CREATED)
async def add_keyword(
    body: KeywordCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {VALID_CATEGORIES}")

    # Check for duplicate
    result = await db.execute(
        select(UserKeyword).where(
            UserKeyword.user_id == current_user.id,
            UserKeyword.keyword == body.keyword,
            UserKeyword.category == body.category,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Keyword already exists in this category")

    kw = UserKeyword(
        user_id=current_user.id,
        keyword=body.keyword,
        category=body.category,
        source=body.source,
        weight=body.weight,
    )
    db.add(kw)
    await db.flush()
    await _maybe_sync_admin(db, current_user)
    return kw


@router.put("/{keyword_id}", response_model=KeywordResponse)
async def update_keyword(
    keyword_id: uuid.UUID,
    body: KeywordUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserKeyword).where(
            UserKeyword.id == keyword_id,
            UserKeyword.user_id == current_user.id,
        )
    )
    kw = result.scalar_one_or_none()
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword not found")

    update_data = body.model_dump(exclude_unset=True)
    if "category" in update_data and update_data["category"] not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {VALID_CATEGORIES}")
    for field, value in update_data.items():
        setattr(kw, field, value)
    await db.flush()
    await _maybe_sync_admin(db, current_user)
    return kw


@router.delete("/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_keyword(
    keyword_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserKeyword).where(
            UserKeyword.id == keyword_id,
            UserKeyword.user_id == current_user.id,
        )
    )
    kw = result.scalar_one_or_none()
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword not found")
    await db.delete(kw)
    await db.flush()
    await _maybe_sync_admin(db, current_user)


@router.post("/bulk", response_model=list[KeywordResponse], status_code=status.HTTP_201_CREATED)
async def bulk_add_keywords(
    body: KeywordBulkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    created = []
    for item in body.keywords:
        if item.category not in VALID_CATEGORIES:
            continue
        # Skip duplicates
        result = await db.execute(
            select(UserKeyword).where(
                UserKeyword.user_id == current_user.id,
                UserKeyword.keyword == item.keyword,
                UserKeyword.category == item.category,
            )
        )
        if result.scalar_one_or_none():
            continue

        kw = UserKeyword(
            user_id=current_user.id,
            keyword=item.keyword,
            category=item.category,
            source=item.source,
            weight=item.weight,
        )
        db.add(kw)
        await db.flush()
        created.append(kw)
    if created:
        await _maybe_sync_admin(db, current_user)
    return created

from __future__ import annotations

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

router = APIRouter(prefix="/keywords", tags=["keywords"])

VALID_CATEGORIES = {"primary", "domain", "career", "faculty", "exclusion", "custom"}


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
    return created

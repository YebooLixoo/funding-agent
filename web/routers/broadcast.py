from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.database import get_db
from web.dependencies import get_current_user
from web.models.broadcast import BroadcastRecipient
from web.models.user import User
from web.schemas.broadcast import BroadcastRecipientCreate, BroadcastRecipientOut

router = APIRouter(prefix="/broadcast", tags=["broadcast"])
public_router = APIRouter(tags=["public"])

MAX_ACTIVE = 25


@router.get("/recipients", response_model=list[BroadcastRecipientOut])
async def list_recipients(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(BroadcastRecipient).where(
                BroadcastRecipient.owner_user_id == user.id
            )
        )
    ).scalars().all()
    return [
        BroadcastRecipientOut(
            id=str(r.id), email=r.email, name=r.name, is_active=r.is_active
        )
        for r in rows
    ]


@router.post(
    "/recipients",
    response_model=BroadcastRecipientOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_recipient(
    body: BroadcastRecipientCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    active_rows = (
        await db.execute(
            select(BroadcastRecipient).where(
                BroadcastRecipient.owner_user_id == user.id,
                BroadcastRecipient.is_active.is_(True),
            )
        )
    ).scalars().all()
    if len(active_rows) >= MAX_ACTIVE:
        raise HTTPException(
            status_code=400,
            detail=f"Recipient limit ({MAX_ACTIVE}) reached",
        )

    row = BroadcastRecipient(
        owner_user_id=user.id,
        email=str(body.email),
        name=body.name,
        is_active=True,
        unsubscribe_token=str(uuid.uuid4()),
    )
    db.add(row)
    await db.flush()
    return BroadcastRecipientOut(
        id=str(row.id), email=row.email, name=row.name, is_active=True
    )


@router.delete(
    "/recipients/{rid}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_recipient(
    rid: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = (
        await db.execute(
            select(BroadcastRecipient).where(
                BroadcastRecipient.id == rid,
                BroadcastRecipient.owner_user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Recipient not found")
    await db.delete(r)
    await db.flush()


@public_router.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe(token: str, db: AsyncSession = Depends(get_db)):
    r = (
        await db.execute(
            select(BroadcastRecipient).where(
                BroadcastRecipient.unsubscribe_token == token
            )
        )
    ).scalar_one_or_none()
    if r and r.is_active:
        r.is_active = False
        r.unsubscribed_at = datetime.now(timezone.utc)
        await db.flush()
    return HTMLResponse("<h1>You have been unsubscribed.</h1>")

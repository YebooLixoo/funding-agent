from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.database import get_db
from web.dependencies import get_current_user
from web.models.chat import ChatMessage
from web.models.keyword import UserKeyword
from web.models.user import User
from web.schemas.chat import ApplyActionsRequest, ChatMessageResponse, ChatRequest, ChatResponse
from web.services.chat import chat_with_user
from web.services.keyword_sync import resync_system_tables

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session_id = body.session_id or str(uuid.uuid4())
    reply, session_id, suggested_actions = await chat_with_user(
        db, current_user.id, body.message, session_id
    )
    return ChatResponse(
        reply=reply,
        session_id=session_id,
        suggested_actions=suggested_actions,
    )


@router.get("/history", response_model=list[ChatMessageResponse])
async def chat_history(
    session_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(ChatMessage).where(ChatMessage.user_id == current_user.id)
    if session_id:
        query = query.where(ChatMessage.session_id == session_id)
    query = query.order_by(ChatMessage.created_at.desc()).limit(100)
    result = await db.execute(query)
    return list(reversed(result.scalars().all()))


@router.post("/apply-actions")
async def apply_actions(
    body: ApplyActionsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.id == body.message_id,
            ChatMessage.user_id == current_user.id,
        )
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if not msg.suggested_actions:
        raise HTTPException(status_code=400, detail="No suggested actions in this message")
    if msg.actions_applied:
        raise HTTPException(status_code=400, detail="Actions already applied")

    actions = msg.suggested_actions.get("actions", [])
    applied = 0

    for action in actions:
        action_type = action.get("type")
        keyword = action.get("keyword", "").strip()
        category = action.get("category", "custom")

        if not keyword:
            continue

        if action_type == "add":
            # Check duplicate
            existing = await db.execute(
                select(UserKeyword).where(
                    UserKeyword.user_id == current_user.id,
                    UserKeyword.keyword == keyword,
                    UserKeyword.category == category,
                )
            )
            if not existing.scalar_one_or_none():
                db.add(UserKeyword(
                    user_id=current_user.id,
                    keyword=keyword,
                    category=category,
                    source="chat",
                    weight=action.get("weight", 1.0),
                ))
                applied += 1

        elif action_type == "remove":
            existing = await db.execute(
                select(UserKeyword).where(
                    UserKeyword.user_id == current_user.id,
                    UserKeyword.keyword == keyword,
                    UserKeyword.category == category,
                )
            )
            kw = existing.scalar_one_or_none()
            if kw:
                await db.delete(kw)
                applied += 1

        elif action_type == "update":
            existing = await db.execute(
                select(UserKeyword).where(
                    UserKeyword.user_id == current_user.id,
                    UserKeyword.keyword == keyword,
                )
            )
            kw = existing.scalar_one_or_none()
            if kw:
                if "weight" in action:
                    kw.weight = action["weight"]
                if "category" in action:
                    kw.category = action["category"]
                applied += 1

    msg.actions_applied = True
    await db.flush()

    # Mirror admin keyword edits into system_* tables — same backstop pattern
    # as ``web/routers/keywords.py::_maybe_sync_admin``. Failures are logged
    # but never raised; ``fetch_runner._load_config`` calls
    # ``resync_system_tables`` again as a backstop.
    if current_user.is_admin:
        try:
            await resync_system_tables(db, current_user.id)
        except Exception:  # noqa: BLE001 — non-fatal, fetch_runner is the backstop
            logger.exception("admin chat-driven keyword sync failed (non-fatal)")

    return {"status": "ok", "applied_count": applied}

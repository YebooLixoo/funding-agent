from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    suggested_actions: dict | None = None


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    session_id: str
    role: str
    content: str
    suggested_actions: dict | None = None
    actions_applied: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ApplyActionsRequest(BaseModel):
    message_id: uuid.UUID

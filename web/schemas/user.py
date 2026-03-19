from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    institution: str | None = None
    department: str | None = None
    position: str | None = None
    research_summary: str | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = None
    institution: str | None = None
    department: str | None = None
    position: str | None = None
    research_summary: str | None = None

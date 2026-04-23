from __future__ import annotations

from pydantic import BaseModel, EmailStr


class BroadcastRecipientCreate(BaseModel):
    email: EmailStr
    name: str | None = None


class BroadcastRecipientOut(BaseModel):
    id: str
    email: EmailStr
    name: str | None
    is_active: bool

    model_config = {"from_attributes": True}

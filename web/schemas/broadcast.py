from __future__ import annotations

from pydantic import BaseModel


class BroadcastRecipientCreate(BaseModel):
    email: str
    name: str | None = None


class BroadcastRecipientOut(BaseModel):
    id: str
    email: str
    name: str | None
    is_active: bool

    model_config = {"from_attributes": True}

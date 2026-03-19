from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class KeywordCreate(BaseModel):
    keyword: str
    category: str  # primary, domain, career, faculty, exclusion, custom
    source: str = "manual"
    weight: float = 1.0


class KeywordUpdate(BaseModel):
    keyword: str | None = None
    category: str | None = None
    weight: float | None = None
    is_active: bool | None = None


class KeywordResponse(BaseModel):
    id: uuid.UUID
    keyword: str
    category: str
    source: str
    weight: float
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class KeywordBulkCreate(BaseModel):
    keywords: list[KeywordCreate]


class KeywordsByCategory(BaseModel):
    primary: list[KeywordResponse] = []
    domain: list[KeywordResponse] = []
    career: list[KeywordResponse] = []
    faculty: list[KeywordResponse] = []
    exclusion: list[KeywordResponse] = []
    custom: list[KeywordResponse] = []

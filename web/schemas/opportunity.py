from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class OpportunityResponse(BaseModel):
    id: uuid.UUID
    composite_id: str
    source: str
    source_id: str
    title: str
    description: str | None = None
    url: str | None = None
    source_type: str | None = None
    deadline: str | None = None
    posted_date: str | None = None
    funding_amount: str | None = None
    keywords: list | None = None
    summary: str | None = None
    opportunity_status: str = "open"
    fetched_at: datetime

    # Per-user fields (populated when user is authenticated)
    relevance_score: float | None = None
    keyword_score: float | None = None
    profile_score: float | None = None
    behavior_score: float | None = None
    urgency_score: float | None = None
    matched_keywords: list | None = None
    is_bookmarked: bool = False
    is_dismissed: bool = False

    model_config = {"from_attributes": True}


class OpportunityListResponse(BaseModel):
    items: list[OpportunityResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class BookmarkRequest(BaseModel):
    pass


class DismissRequest(BaseModel):
    pass

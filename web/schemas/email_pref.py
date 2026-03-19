from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class EmailPrefResponse(BaseModel):
    id: uuid.UUID
    is_subscribed: bool
    frequency: str
    day_of_week: int
    time_of_day: str
    min_relevance_score: float
    deadline_lookahead_days: int
    last_sent_at: datetime | None = None

    model_config = {"from_attributes": True}


class EmailPrefUpdate(BaseModel):
    is_subscribed: bool | None = None
    frequency: str | None = None
    day_of_week: int | None = None
    time_of_day: str | None = None
    min_relevance_score: float | None = None
    deadline_lookahead_days: int | None = None


class EmailHistoryResponse(BaseModel):
    id: uuid.UUID
    sent_at: datetime
    opportunity_count: int
    success: bool
    error_msg: str | None = None

    model_config = {"from_attributes": True}

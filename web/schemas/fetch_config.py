from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class FetchConfigResponse(BaseModel):
    id: uuid.UUID
    sources_enabled: dict | None = None
    custom_search_terms: list | None = None
    fetch_frequency: str
    last_fetched_at: datetime | None = None

    model_config = {"from_attributes": True}


class FetchConfigUpdate(BaseModel):
    sources_enabled: dict | None = None
    custom_search_terms: list | None = None
    fetch_frequency: str | None = None

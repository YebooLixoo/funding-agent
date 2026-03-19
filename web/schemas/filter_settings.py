from __future__ import annotations

import uuid

from pydantic import BaseModel


class FilterSettingsResponse(BaseModel):
    id: uuid.UUID
    keyword_threshold: float
    llm_threshold: float
    use_llm_filter: bool
    sources_enabled: dict | None = None

    model_config = {"from_attributes": True}


class FilterSettingsUpdate(BaseModel):
    keyword_threshold: float | None = None
    llm_threshold: float | None = None
    use_llm_filter: bool | None = None
    sources_enabled: dict | None = None

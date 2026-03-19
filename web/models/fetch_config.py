from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from web.database import Base


class UserFetchConfig(Base):
    __tablename__ = "user_fetch_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    sources_enabled: Mapped[dict | None] = mapped_column(JSON)
    custom_search_terms: Mapped[list | None] = mapped_column(JSON)
    fetch_frequency: Mapped[str] = mapped_column(String(16), default="weekly")
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User", back_populates="fetch_config")

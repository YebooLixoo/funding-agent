from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from web.database import Base


class UserFilterSettings(Base):
    __tablename__ = "user_filter_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    keyword_threshold: Mapped[float] = mapped_column(Float, default=0.3)
    llm_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    use_llm_filter: Mapped[bool] = mapped_column(Boolean, default=True)
    sources_enabled: Mapped[dict | None] = mapped_column(JSON)

    user = relationship("User", back_populates="filter_settings")

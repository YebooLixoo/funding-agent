from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from web.database import Base


class UserEmailPref(Base):
    __tablename__ = "user_email_prefs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=True)
    frequency: Mapped[str] = mapped_column(String(16), default="weekly")  # daily, weekly, biweekly
    day_of_week: Mapped[int] = mapped_column(Integer, default=4)  # 0=Mon, 4=Thu
    time_of_day: Mapped[str] = mapped_column(String(8), default="20:00")
    min_relevance_score: Mapped[float] = mapped_column(Float, default=0.3)
    deadline_lookahead_days: Mapped[int] = mapped_column(Integer, default=30)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User", back_populates="email_pref")


class UserEmailHistory(Base):
    __tablename__ = "user_email_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    opportunity_count: Mapped[int] = mapped_column(Integer, default=0)
    opportunity_ids: Mapped[list | None] = mapped_column(JSON)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_msg: Mapped[str | None] = mapped_column(Text)

    user = relationship("User", back_populates="email_history")

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from web.database import Base


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    composite_id: Mapped[str] = mapped_column(String(512), unique=True, index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2048))
    source_type: Mapped[str | None] = mapped_column(String(32))  # government, industry
    deadline: Mapped[str | None] = mapped_column(String(128))
    posted_date: Mapped[str | None] = mapped_column(String(128))
    funding_amount: Mapped[str | None] = mapped_column(String(256))
    keywords: Mapped[list | None] = mapped_column(JSON)
    summary: Mapped[str | None] = mapped_column(Text)
    opportunity_status: Mapped[str] = mapped_column(String(32), default="open", server_default="open")
    deadline_type: Mapped[str] = mapped_column(String(32), default="fixed", server_default="fixed")
    # Compute resource fields
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resource_scale: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allocation_details: Mapped[str | None] = mapped_column(String(512), nullable=True)
    eligibility: Mapped[str | None] = mapped_column(String(256), nullable=True)
    access_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fetched_for_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class UserOpportunityScore(Base):
    __tablename__ = "user_opportunity_scores"
    __table_args__ = (
        UniqueConstraint("user_id", "opportunity_id", name="uq_user_opportunity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    matched_keywords: Mapped[list | None] = mapped_column(JSON)
    keyword_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    profile_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    behavior_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    urgency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_bookmarked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    view_count: Mapped[int] = mapped_column(default=0, server_default="0")
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="opportunity_scores")
    opportunity = relationship("Opportunity")

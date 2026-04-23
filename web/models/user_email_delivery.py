from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from web.database import Base


class UserEmailDelivery(Base):
    __tablename__ = "user_email_deliveries"
    __table_args__ = (
        UniqueConstraint("user_id", "opportunity_id", name="uq_user_opp_delivery"),
        Index("ix_user_email_deliveries_user_sent", "user_id", "sent_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from web.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    full_name: Mapped[str] = mapped_column(String(256), nullable=False)
    institution: Mapped[str | None] = mapped_column(String(512))
    department: Mapped[str | None] = mapped_column(String(256))
    position: Mapped[str | None] = mapped_column(String(128))
    research_summary: Mapped[str | None] = mapped_column(String(2000))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    documents = relationship("UserDocument", back_populates="user", cascade="all, delete-orphan")
    keywords = relationship("UserKeyword", back_populates="user", cascade="all, delete-orphan")
    filter_settings = relationship(
        "UserFilterSettings", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    opportunity_scores = relationship(
        "UserOpportunityScore", back_populates="user", cascade="all, delete-orphan"
    )
    email_pref = relationship(
        "UserEmailPref", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    email_history = relationship(
        "UserEmailHistory", back_populates="user", cascade="all, delete-orphan"
    )
    fetch_config = relationship(
        "UserFetchConfig", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")

"""Per-user email scheduling service.

Imports the internal Emailer for actual sending.
This module is designed to be called from a background scheduler (e.g., Celery beat).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.models.email_pref import UserEmailHistory, UserEmailPref
from web.models.opportunity import Opportunity, UserOpportunityScore
from web.models.user import User

logger = logging.getLogger(__name__)


async def get_users_due_for_email(db: AsyncSession) -> list[User]:
    """Find users who are due for an email digest based on their preferences."""
    result = await db.execute(
        select(UserEmailPref).where(UserEmailPref.is_subscribed.is_(True))
    )
    prefs = result.scalars().all()

    due_users = []
    now = datetime.now(timezone.utc)

    for pref in prefs:
        if pref.last_sent_at is None:
            # Never sent — send now
            due_users.append(pref.user_id)
            continue

        # Check frequency
        days_since = (now - pref.last_sent_at).days
        if pref.frequency == "daily" and days_since >= 1:
            due_users.append(pref.user_id)
        elif pref.frequency == "weekly" and days_since >= 7:
            due_users.append(pref.user_id)
        elif pref.frequency == "biweekly" and days_since >= 14:
            due_users.append(pref.user_id)

    # Fetch user objects
    if not due_users:
        return []

    user_result = await db.execute(
        select(User).where(User.id.in_(due_users), User.is_active.is_(True))
    )
    return list(user_result.scalars().all())


async def get_opportunities_for_user(
    db: AsyncSession, user_id, min_score: float = 0.3
) -> list[tuple[Opportunity, UserOpportunityScore]]:
    """Get scored opportunities above threshold for a user."""
    result = await db.execute(
        select(UserOpportunityScore, Opportunity)
        .join(Opportunity, UserOpportunityScore.opportunity_id == Opportunity.id)
        .where(
            UserOpportunityScore.user_id == user_id,
            UserOpportunityScore.relevance_score >= min_score,
            UserOpportunityScore.is_dismissed.is_(False),
        )
        .order_by(UserOpportunityScore.relevance_score.desc())
        .limit(50)
    )
    return [(row.Opportunity, row.UserOpportunityScore) for row in result.all()]


async def record_email_sent(
    db: AsyncSession,
    user_id,
    opportunity_count: int,
    opportunity_ids: list[str],
    success: bool,
    error_msg: str | None = None,
):
    """Record an email send attempt."""
    history = UserEmailHistory(
        user_id=user_id,
        opportunity_count=opportunity_count,
        opportunity_ids=opportunity_ids,
        success=success,
        error_msg=error_msg,
    )
    db.add(history)

    if success:
        # Update last_sent_at
        pref_result = await db.execute(
            select(UserEmailPref).where(UserEmailPref.user_id == user_id)
        )
        pref = pref_result.scalar_one_or_none()
        if pref:
            pref.last_sent_at = datetime.now(timezone.utc)

    await db.flush()

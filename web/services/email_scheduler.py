"""Per-user email scheduling service.

Imports the internal Emailer for actual sending.
This module is designed to be called from a background scheduler (e.g., Celery beat).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.models.email_pref import UserEmailHistory, UserEmailPref
from web.models.opportunity import Opportunity, UserOpportunityScore
from web.models.user import User
from web.models.user_email_delivery import UserEmailDelivery

logger = logging.getLogger(__name__)

# Frequency name → days between sends. Used together with the scheduled slot
# (day_of_week + time_of_day) to decide whether a user is due.
_FREQUENCY_DAYS = {"daily": 1, "weekly": 7, "biweekly": 14}


async def get_users_due_for_email(
    db: AsyncSession, *, now: datetime | None = None
) -> list[User]:
    """Return active+subscribed users whose digest is due at ``now``.

    Honors UserEmailPref.frequency, day_of_week (0=Mon..6=Sun, matching
    Python's datetime.weekday()), and time_of_day ('HH:MM'). A user is due if:

      - they are subscribed (is_subscribed=True) AND
      - they are active (User.is_active=True) AND
      - now >= scheduled-slot for the current week (computed from day_of_week +
        time_of_day) AND
      - their last_sent_at is None OR (now - last_sent_at).days >=
        frequency_days - 1 (the -1 buffer prevents missing the slot due to
        second-by-second drift around the exact send time).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    result = await db.execute(
        select(UserEmailPref).where(UserEmailPref.is_subscribed.is_(True))
    )
    prefs = result.scalars().all()

    due_user_ids = []
    for pref in prefs:
        gap = _FREQUENCY_DAYS.get(pref.frequency, 7)
        if pref.last_sent_at is not None:
            # SQLite drops tz info on round-trip; treat any naive datetime from
            # the DB as UTC so the subtraction below is always well-defined.
            last_sent = pref.last_sent_at
            if last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=timezone.utc)
            # Absolute next-send cutoff: after a send at ``last_sent`` with
            # frequency ``gap`` days, the next send is allowed at
            # ``last_sent + gap days`` (combined with the slot check below).
            # This avoids the off-by-one ``elapsed_days < gap - 1`` bug that
            # made daily users due every hour after their first send.
            if now < last_sent + timedelta(days=gap):
                continue
        if not _now_is_at_or_after_scheduled_slot(pref, now):
            continue
        due_user_ids.append(pref.user_id)

    if not due_user_ids:
        return []

    user_result = await db.execute(
        select(User).where(User.id.in_(due_user_ids), User.is_active.is_(True))
    )
    return list(user_result.scalars().all())


def _now_is_at_or_after_scheduled_slot(pref: UserEmailPref, now: datetime) -> bool:
    """True if ``now`` is past the scheduled slot for the current week.

    The slot is ``day_of_week`` (0=Mon..6=Sun, matching Python's
    ``datetime.weekday()``) at ``time_of_day`` ('HH:MM'). After that slot, the
    user remains "due" through the rest of the week until their next frequency
    window starts (gated by ``last_sent_at`` in the caller).
    """
    try:
        h, m = (int(x) for x in pref.time_of_day.split(":"))
    except (AttributeError, ValueError):
        # Defensive: treat malformed time_of_day as midnight.
        h, m = 0, 0
    scheduled_dow = pref.day_of_week
    today_dow = now.weekday()
    if today_dow < scheduled_dow:
        return False
    if today_dow == scheduled_dow:
        return (now.hour, now.minute) >= (h, m)
    return True


async def get_undelivered_opportunity_ids(
    db: AsyncSession, user_id, candidate_opportunity_ids: list
) -> list:
    """Filter ``candidate_opportunity_ids`` to those not yet delivered to ``user_id``.

    Looks up rows in ``user_email_deliveries`` for the given user/opportunity
    pairs and returns the input list with any already-delivered ids removed,
    preserving original order.
    """
    if not candidate_opportunity_ids:
        return []
    result = await db.execute(
        select(UserEmailDelivery.opportunity_id).where(
            UserEmailDelivery.user_id == user_id,
            UserEmailDelivery.opportunity_id.in_(candidate_opportunity_ids),
        )
    )
    delivered_set = set(result.scalars().all())
    return [oid for oid in candidate_opportunity_ids if oid not in delivered_set]


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

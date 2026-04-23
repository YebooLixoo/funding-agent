"""Per-user digest dispatch (Task 12).

Orchestrates one round of due-user digest sends. Per user we:
  1. Pull scored, undismissed opportunities above their min_relevance_score.
  2. Filter out anything already in ``user_email_deliveries`` for that user.
  3. Expand recipients to ``user.email`` plus the user's *active* broadcast
     list. The owner's own copy gets no unsubscribe link; broadcast copies
     each carry their personal token.
  4. Send via SMTP, write ``UserEmailDelivery`` + ``UserEmailHistory``,
     update ``UserEmailPref.last_sent_at``.

Multi-session boundary contract (mirrors ``fetch_runner``):
  * One short async session for "fetch users due".
  * One short async session per user for the dispatch + writes.
  * One short async session for the static history regeneration query
    (admin-only, runs after all users are processed).

This contract is what makes ``tests/conftest.py``'s ``async_session``
monkeypatch work — every session opens via the patched factory and shares
the in-memory engine with the test's ``db_session`` fixture.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from src.emailer import Emailer
from src.history_generator import HistoryGenerator
from web.config import get_settings
from web.database import async_session
from web.models.broadcast import BroadcastRecipient
from web.models.email_pref import UserEmailHistory, UserEmailPref
from web.models.opportunity import Opportunity, UserOpportunityScore
from web.models.user import User
from web.models.user_email_delivery import UserEmailDelivery
from web.services.email_compose_adapter import group_by_source_type
from web.services.email_scheduler import (
    get_undelivered_opportunity_ids,
    get_users_due_for_email,
)
from web.services.history_data_source import (
    PlatformDBSource,
    fetch_admin_emailed_opportunities,
)

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    user_id: Any
    sent: int
    success: bool


# --- Public entry points ---------------------------------------------------


async def dispatch_due_users(now: datetime | None = None) -> list[DispatchResult]:
    """Dispatch a digest to every user whose schedule slot has fired.

    After all users are processed, regenerate the static history page IFF the
    admin user was among them (the static page mirrors the admin's delivery
    log, so other users' sends don't change it).
    """
    settings = get_settings()
    now_dt = now or datetime.now(timezone.utc)

    async with async_session() as s:
        users = await get_users_due_for_email(s, now=now_dt)

    results: list[DispatchResult] = []
    admin_processed = False
    for user in users:
        async with async_session() as s:
            res = await _dispatch_one(s, user, settings, test_mode=False)
            await s.commit()
        results.append(res)
        if user.email == settings.admin_email:
            admin_processed = True

    if admin_processed:
        await _regenerate_admin_history(settings)

    return results


async def dispatch_one_user(
    user_email: str, *, test_mode: bool = False
) -> list[DispatchResult]:
    """Dispatch to a single user (manual CLI/API trigger).

    In ``test_mode`` we skip the broadcast list and roll back instead of
    committing — useful for "preview my next digest" flows that should not
    permanently mark opportunities as delivered.
    """
    settings = get_settings()
    async with async_session() as s:
        user = (
            await s.execute(
                select(User).where(
                    User.email == user_email, User.is_active.is_(True)
                )
            )
        ).scalar_one()
        res = await _dispatch_one(s, user, settings, test_mode=test_mode)
        if test_mode:
            await s.rollback()
        else:
            await s.commit()

    if not test_mode and user.email == settings.admin_email:
        await _regenerate_admin_history(settings)
    return [res]


# --- Internal helpers ------------------------------------------------------


async def _dispatch_one(s, user, settings, *, test_mode: bool) -> DispatchResult:
    pref = (
        await s.execute(
            select(UserEmailPref).where(UserEmailPref.user_id == user.id)
        )
    ).scalar_one_or_none()
    if pref is None or not pref.is_subscribed:
        return DispatchResult(user.id, 0, True)

    rows = (
        await s.execute(
            select(Opportunity, UserOpportunityScore)
            .join(
                UserOpportunityScore,
                UserOpportunityScore.opportunity_id == Opportunity.id,
            )
            .where(
                UserOpportunityScore.user_id == user.id,
                UserOpportunityScore.relevance_score >= pref.min_relevance_score,
                UserOpportunityScore.is_dismissed.is_(False),
            )
        )
    ).all()
    candidate_ids = [opp.id for opp, _score in rows]
    if not candidate_ids:
        return DispatchResult(user.id, 0, True)

    new_ids = set(
        await get_undelivered_opportunity_ids(s, user.id, candidate_ids)
    )
    rows_to_send = [(opp, score) for opp, score in rows if opp.id in new_ids]
    if not rows_to_send:
        return DispatchResult(user.id, 0, True)

    grouped = group_by_source_type(rows_to_send)

    # In test mode we deliberately omit the broadcast list — it's a "preview
    # what I'd get" flow, not a real broadcast.
    bcasts = (
        []
        if test_mode
        else (
            await s.execute(
                select(BroadcastRecipient).where(
                    BroadcastRecipient.owner_user_id == user.id,
                    BroadcastRecipient.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )

    emailer = Emailer(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        use_tls=True,
        archive_dir="outputs/digests",
    )
    date_str = datetime.now().strftime("%B %d, %Y")
    history_url = settings.history_url or None

    compose_kwargs = dict(
        government_opps=grouped.get("government_opps", []),
        industry_opps=grouped.get("industry_opps", []),
        university_opps=grouped.get("university_opps", []),
        compute_opps=grouped.get("compute_opps", []),
        upcoming_deadlines=[],
        date_str=date_str,
        history_url=history_url,
    )

    n = len(rows_to_send)
    subject = (
        f"Funding Digest: {date_str} "
        f"({n} opportunit{'y' if n == 1 else 'ies'})"
    )

    success = True
    recipients: list[tuple[str, str | None]] = [(user.email, None)] + [
        (b.email, b.unsubscribe_token) for b in bcasts
    ]
    for recipient_email, token in recipients:
        try:
            html = emailer.compose(unsubscribe_token=token, **compose_kwargs)
        except TypeError:
            # Defensive: legacy compose() without unsubscribe_token kwarg.
            html = emailer.compose(**compose_kwargs)
        ok = emailer.send(
            recipients=[recipient_email],
            subject=subject,
            html_body=html,
        )
        success = success and bool(ok)

    if not test_mode:
        for opp_id in new_ids:
            s.add(
                UserEmailDelivery(user_id=user.id, opportunity_id=opp_id)
            )
        s.add(
            UserEmailHistory(
                user_id=user.id,
                sent_at=datetime.now(timezone.utc),
                opportunity_count=len(new_ids),
                opportunity_ids=[str(i) for i in new_ids],
                success=success,
            )
        )
        pref.last_sent_at = datetime.now(timezone.utc)

    return DispatchResult(user.id, len(new_ids), success)


async def _regenerate_admin_history(settings) -> None:
    """Re-render the static admin history page from the platform DB."""
    async with async_session() as s:
        rows = await fetch_admin_emailed_opportunities(s, settings.admin_email)
    HistoryGenerator(output_dir="docs").generate(PlatformDBSource(rows))

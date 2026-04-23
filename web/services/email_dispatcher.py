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
    admin_success = False
    for user in users:
        async with async_session() as s:
            # _dispatch_one owns its commit (outbox-before-send pattern).
            res = await _dispatch_one(s, user, settings, test_mode=False)
        results.append(res)
        # Only re-render the static admin history if the admin's own send
        # actually succeeded. A failed admin send must NOT cause us to publish
        # a stale-page; the deliveries table is the source of truth for the
        # "what got emailed" log.
        if user.email == settings.admin_email and res.success:
            admin_success = True

    if admin_success:
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
        # _dispatch_one owns its own commit in real mode (outbox-before-send).
        # In test_mode it writes nothing and we roll back for safety.
        res = await _dispatch_one(s, user, settings, test_mode=test_mode)
        if test_mode:
            await s.rollback()

    if not test_mode and user.email == settings.admin_email and res.success:
        await _regenerate_admin_history(settings)
    return [res]


# --- Internal helpers ------------------------------------------------------


async def _dispatch_one(s, user, settings, *, test_mode: bool) -> DispatchResult:
    """Outbox-pattern dispatch: persist deliveries BEFORE sending.

    The previous order (send → commit) had a hole: if commit failed after a
    successful SMTP send, no delivery rows persisted and the next hourly run
    re-sent the same opportunities. We now write ``UserEmailDelivery`` +
    ``UserEmailHistory`` + advance ``pref.last_sent_at`` and commit FIRST,
    then send. If send fails we log it; the trade-off is "miss a notification
    once" rather than "spam every hour after a transient SMTP blip".
    """
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

    # --- OUTBOX: persist intent BEFORE sending. -----------------------------
    # If commit fails here, send is never attempted and the next run will
    # naturally retry. If commit succeeds and the subsequent send fails, the
    # user misses one notification — accepted as the lesser evil vs. hourly
    # re-spam after a transient SMTP error.
    if not test_mode:
        for opp_id in new_ids:
            s.add(UserEmailDelivery(user_id=user.id, opportunity_id=opp_id))
        s.add(
            UserEmailHistory(
                user_id=user.id,
                sent_at=datetime.now(timezone.utc),
                opportunity_count=len(new_ids),
                opportunity_ids=[str(i) for i in new_ids],
                success=True,  # optimistic; failure is logged below
            )
        )
        pref.last_sent_at = datetime.now(timezone.utc)
        await s.commit()

    # --- NOW send. Failures are logged but do NOT roll back the outbox. -----
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
        app_base_url=settings.app_base_url or None,
    )

    n = len(rows_to_send)
    subject = (
        f"Funding Digest: {date_str} "
        f"({n} opportunit{'y' if n == 1 else 'ies'})"
    )

    owner_success: bool | None = None
    broadcast_success_count = 0
    broadcast_failure_count = 0

    recipients: list[tuple[bool, str, str | None]] = [(True, user.email, None)] + [
        (False, b.email, b.unsubscribe_token) for b in bcasts
    ]
    for is_owner, recipient_email, token in recipients:
        try:
            html = emailer.compose(unsubscribe_token=token, **compose_kwargs)
        except TypeError:
            # Defensive: legacy compose() without unsubscribe_token kwarg.
            html = emailer.compose(**compose_kwargs)
        try:
            ok = emailer.send(
                recipients=[recipient_email],
                subject=subject,
                html_body=html,
            )
        except Exception:  # noqa: BLE001 — surfaced as a logged failure
            logger.exception("send raised for %s", recipient_email)
            ok = False
        if is_owner:
            owner_success = bool(ok)
        else:
            if ok:
                broadcast_success_count += 1
            else:
                broadcast_failure_count += 1

    if not test_mode and owner_success is False:
        logger.error(
            "owner send failed for %s; deliveries already persisted "
            "(%d opps). User will not see this digest. "
            "Broadcast: %d ok, %d failed.",
            user.email,
            len(new_ids),
            broadcast_success_count,
            broadcast_failure_count,
        )
        # Annotate the audit trail with a follow-up failure row in a fresh
        # session so the optimistic success row above stays intact and the
        # error is visible to admins.
        async with async_session() as s2:
            s2.add(
                UserEmailHistory(
                    user_id=user.id,
                    sent_at=datetime.now(timezone.utc),
                    opportunity_count=0,
                    opportunity_ids=[],
                    success=False,
                    error_msg=(
                        f"owner SMTP failed; {len(new_ids)} opps marked "
                        f"delivered without send"
                    ),
                )
            )
            await s2.commit()

    sent_count = len(new_ids) if owner_success else 0
    return DispatchResult(user.id, sent_count, bool(owner_success))


async def _regenerate_admin_history(settings) -> None:
    """Re-render the static admin history page from the platform DB."""
    async with async_session() as s:
        rows = await fetch_admin_emailed_opportunities(s, settings.admin_email)
    HistoryGenerator(output_dir="docs").generate(PlatformDBSource(rows))

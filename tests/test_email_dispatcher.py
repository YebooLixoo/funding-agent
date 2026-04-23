"""Tests for web.services.email_dispatcher (Task 12).

Verify that ``dispatch_one_user`` and ``dispatch_due_users`` correctly:
  - skip users not due,
  - send to user + active broadcast list (not inactive recipients),
  - render an unsubscribe link only for broadcast copies (not the owner's),
  - write ``UserEmailDelivery`` rows in real mode but NOT in test mode,
  - skip already-delivered opportunities.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from web.models.broadcast import BroadcastRecipient
from web.models.email_pref import UserEmailHistory, UserEmailPref
from web.models.opportunity import Opportunity, UserOpportunityScore
from web.models.user import User
from web.models.user_email_delivery import UserEmailDelivery
from web.services.email_dispatcher import dispatch_due_users, dispatch_one_user


@pytest.mark.asyncio
async def test_dispatch_skips_users_not_due(db_session):
    # No subscribed users → empty result list
    results = await dispatch_due_users(
        now=datetime(2026, 4, 16, 20, 0, tzinfo=timezone.utc)
    )
    assert results == []


@pytest.mark.asyncio
async def test_dispatch_one_user_sends_to_user_plus_active_broadcast_list(
    db_session, admin_user
):
    bcasts = [
        BroadcastRecipient(
            owner_user_id=admin_user.id,
            email="bcast1@x",
            name="B1",
            is_active=True,
            unsubscribe_token=str(_uuid.uuid4()),
        ),
        BroadcastRecipient(
            owner_user_id=admin_user.id,
            email="bcast2@x",
            name="B2",
            is_active=True,
            unsubscribe_token=str(_uuid.uuid4()),
        ),
        BroadcastRecipient(
            owner_user_id=admin_user.id,
            email="inactive@x",
            name="I",
            is_active=False,
            unsubscribe_token=str(_uuid.uuid4()),
        ),
    ]
    pref = UserEmailPref(
        user_id=admin_user.id,
        is_subscribed=True,
        frequency="weekly",
        day_of_week=3,
        time_of_day="20:00",
        min_relevance_score=0.3,
        last_sent_at=None,
    )
    opp = Opportunity(
        composite_id="nsf_X1",
        source="nsf",
        source_id="X1",
        title="ML Grant",
        description="d",
        url="https://e.com/1",
        source_type="government",
        summary="auto",
    )
    db_session.add_all(bcasts + [pref, opp])
    await db_session.flush()
    db_session.add(
        UserOpportunityScore(
            user_id=admin_user.id, opportunity_id=opp.id, relevance_score=0.7
        )
    )
    await db_session.commit()

    sent_to: list[tuple[str, bool]] = []

    def _capture_send(self, recipients, subject, html_body):
        sent_to.append((recipients[0], "unsubscribe" in (html_body or "").lower()))
        return True

    with patch(
        "web.services.email_dispatcher.HistoryGenerator"
    ) as mock_hg, patch("src.emailer.Emailer.send", new=_capture_send):
        mock_hg.return_value.generate.return_value = None
        results = await dispatch_one_user(admin_user.email, test_mode=False)

    assert len(results) == 1 and results[0].sent == 1
    emails = {r[0] for r in sent_to}
    assert emails == {admin_user.email, "bcast1@x", "bcast2@x"}
    assert "inactive@x" not in emails
    has_unsub = {email: had_link for email, had_link in sent_to}
    assert has_unsub[admin_user.email] is False
    assert has_unsub["bcast1@x"] is True
    assert has_unsub["bcast2@x"] is True


@pytest.mark.asyncio
async def test_dispatch_writes_user_email_deliveries(db_session, admin_user):
    pref = UserEmailPref(
        user_id=admin_user.id,
        is_subscribed=True,
        frequency="weekly",
        day_of_week=3,
        time_of_day="20:00",
        min_relevance_score=0.3,
    )
    opp = Opportunity(
        composite_id="nsf_Y1",
        source="nsf",
        source_id="Y1",
        title="T",
        description="d",
        url="https://e.com/y",
        source_type="government",
    )
    db_session.add_all([pref, opp])
    await db_session.flush()
    db_session.add(
        UserOpportunityScore(
            user_id=admin_user.id, opportunity_id=opp.id, relevance_score=0.5
        )
    )
    await db_session.commit()

    with patch(
        "web.services.email_dispatcher.HistoryGenerator"
    ) as mock_hg, patch("src.emailer.Emailer.send", return_value=True):
        mock_hg.return_value.generate.return_value = None
        await dispatch_one_user(admin_user.email, test_mode=False)

    deliveries = (
        await db_session.execute(select(UserEmailDelivery))
    ).scalars().all()
    assert len(deliveries) == 1
    assert deliveries[0].opportunity_id == opp.id

    # UserEmailHistory recorded too
    history = (await db_session.execute(select(UserEmailHistory))).scalars().all()
    assert len(history) == 1
    assert history[0].opportunity_count == 1
    assert history[0].success is True


@pytest.mark.asyncio
async def test_dispatch_skips_already_delivered_opps(db_session, admin_user):
    pref = UserEmailPref(
        user_id=admin_user.id,
        is_subscribed=True,
        frequency="weekly",
        day_of_week=3,
        time_of_day="20:00",
        min_relevance_score=0.3,
    )
    opp = Opportunity(
        composite_id="nsf_Z1",
        source="nsf",
        source_id="Z1",
        title="T",
        description="d",
        url="https://e.com/z",
        source_type="government",
    )
    db_session.add_all([pref, opp])
    await db_session.flush()
    db_session.add(
        UserOpportunityScore(
            user_id=admin_user.id, opportunity_id=opp.id, relevance_score=0.5
        )
    )
    db_session.add(UserEmailDelivery(user_id=admin_user.id, opportunity_id=opp.id))
    await db_session.commit()

    with patch(
        "web.services.email_dispatcher.HistoryGenerator"
    ) as mock_hg, patch("src.emailer.Emailer.send") as mock_send:
        mock_hg.return_value.generate.return_value = None
        result = await dispatch_one_user(admin_user.email, test_mode=False)

    assert result[0].sent == 0
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_test_mode_does_not_write_deliveries(db_session, admin_user):
    pref = UserEmailPref(
        user_id=admin_user.id,
        is_subscribed=True,
        frequency="weekly",
        day_of_week=3,
        time_of_day="20:00",
        min_relevance_score=0.3,
    )
    opp = Opportunity(
        composite_id="nsf_W1",
        source="nsf",
        source_id="W1",
        title="T",
        description="d",
        url="https://e.com/w",
        source_type="government",
    )
    db_session.add_all([pref, opp])
    await db_session.flush()
    db_session.add(
        UserOpportunityScore(
            user_id=admin_user.id, opportunity_id=opp.id, relevance_score=0.5
        )
    )
    await db_session.commit()

    with patch("src.emailer.Emailer.send", return_value=True):
        await dispatch_one_user(admin_user.email, test_mode=True)

    deliveries = (
        await db_session.execute(select(UserEmailDelivery))
    ).scalars().all()
    assert deliveries == []  # test mode does not persist

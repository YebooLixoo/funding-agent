"""Tests for email_scheduler due-logic rewrite (Task 10).

Verify that get_users_due_for_email honors UserEmailPref.day_of_week and
time_of_day in addition to frequency, and that get_undelivered_opportunity_ids
correctly filters out opportunities already in user_email_deliveries.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from web.models.user import User
from web.models.email_pref import UserEmailPref
from web.services.email_scheduler import (
    get_users_due_for_email,
    get_undelivered_opportunity_ids,
)


@pytest.mark.asyncio
async def test_weekly_thursday_8pm_due_only_on_or_after_scheduled_slot(db_session):
    u = User(email="a@x", password_hash="x", full_name="A", is_active=True)
    db_session.add(u)
    await db_session.flush()
    db_session.add(
        UserEmailPref(
            user_id=u.id,
            is_subscribed=True,
            frequency="weekly",
            day_of_week=3,
            time_of_day="20:00",
            last_sent_at=None,  # Python weekday: 0=Mon, 3=Thu
        )
    )
    await db_session.flush()

    # 2026-04-16 is a Thursday
    thu_8pm = datetime(2026, 4, 16, 20, 0, tzinfo=timezone.utc)
    fri_8am = datetime(2026, 4, 17, 8, 0, tzinfo=timezone.utc)
    wed_8pm = datetime(2026, 4, 15, 20, 0, tzinfo=timezone.utc)
    thu_7pm = datetime(2026, 4, 16, 19, 0, tzinfo=timezone.utc)

    assert (await get_users_due_for_email(db_session, now=wed_8pm)) == []
    assert (await get_users_due_for_email(db_session, now=thu_7pm)) == []
    assert len(await get_users_due_for_email(db_session, now=thu_8pm)) == 1
    assert len(await get_users_due_for_email(db_session, now=fri_8am)) == 1


@pytest.mark.asyncio
async def test_no_double_send_within_frequency_window(db_session):
    u = User(email="b@x", password_hash="x", full_name="B", is_active=True)
    db_session.add(u)
    await db_session.flush()
    last_sent = datetime(2026, 4, 16, 20, 0, tzinfo=timezone.utc)
    db_session.add(
        UserEmailPref(
            user_id=u.id,
            is_subscribed=True,
            frequency="weekly",
            day_of_week=3,
            time_of_day="20:00",
            last_sent_at=last_sent,
        )
    )
    await db_session.flush()
    # 1 hour later — same week, should not re-send
    assert (
        await get_users_due_for_email(db_session, now=last_sent + timedelta(hours=1))
    ) == []
    # 7 days later — new week's slot
    next_thu_8pm = datetime(2026, 4, 23, 20, 0, tzinfo=timezone.utc)
    assert len(await get_users_due_for_email(db_session, now=next_thu_8pm)) == 1


@pytest.mark.asyncio
async def test_unsubscribed_user_not_due(db_session):
    u = User(email="c@x", password_hash="x", full_name="C", is_active=True)
    db_session.add(u)
    await db_session.flush()
    db_session.add(
        UserEmailPref(
            user_id=u.id,
            is_subscribed=False,
            frequency="weekly",
            day_of_week=3,
            time_of_day="20:00",
            last_sent_at=None,
        )
    )
    await db_session.flush()
    thu_8pm = datetime(2026, 4, 16, 20, 0, tzinfo=timezone.utc)
    assert (await get_users_due_for_email(db_session, now=thu_8pm)) == []


@pytest.mark.asyncio
async def test_inactive_user_not_due(db_session):
    u = User(email="d@x", password_hash="x", full_name="D", is_active=False)
    db_session.add(u)
    await db_session.flush()
    db_session.add(
        UserEmailPref(
            user_id=u.id,
            is_subscribed=True,
            frequency="weekly",
            day_of_week=3,
            time_of_day="20:00",
            last_sent_at=None,
        )
    )
    await db_session.flush()
    thu_8pm = datetime(2026, 4, 16, 20, 0, tzinfo=timezone.utc)
    assert (await get_users_due_for_email(db_session, now=thu_8pm)) == []


@pytest.mark.asyncio
async def test_undelivered_filter(db_session):
    from web.models.opportunity import Opportunity
    from web.models.user_email_delivery import UserEmailDelivery

    u = User(email="e@x", password_hash="x", full_name="E", is_active=True)
    o1 = Opportunity(composite_id="x_1", source="x", source_id="1", title="O1")
    o2 = Opportunity(composite_id="x_2", source="x", source_id="2", title="O2")
    db_session.add_all([u, o1, o2])
    await db_session.flush()
    db_session.add(UserEmailDelivery(user_id=u.id, opportunity_id=o1.id))
    await db_session.flush()

    result = await get_undelivered_opportunity_ids(db_session, u.id, [o1.id, o2.id])
    assert o2.id in result
    assert o1.id not in result


@pytest.mark.asyncio
async def test_undelivered_filter_empty_input(db_session):
    u = User(email="f@x", password_hash="x", full_name="F", is_active=True)
    db_session.add(u)
    await db_session.flush()
    assert await get_undelivered_opportunity_ids(db_session, u.id, []) == []

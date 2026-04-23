"""Tests for email_scheduler due-logic rewrite (Task 10).

Verify that get_users_due_for_email honors UserEmailPref.day_of_week and
time_of_day in addition to frequency, and that get_undelivered_opportunity_ids
correctly filters out opportunities already in user_email_deliveries.

NOTE on timezone math: ``time_of_day`` is interpreted in
``email_scheduler.SCHEDULER_TIMEZONE`` (America/Denver). UTC inputs are
converted before slot comparison. April is in MDT (UTC-6), so e.g.
"20:00 MT Thu Apr 16, 2026" == "02:00 UTC Fri Apr 17, 2026".
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

    # All UTC datetimes below are anchored so the local-MT clock matches the
    # variable name. 2026-04-16 is a Thursday (MT). MDT = UTC-6.
    thu_8pm = datetime(2026, 4, 17, 2, 0, tzinfo=timezone.utc)   # = 20:00 MDT Thu
    fri_8am = datetime(2026, 4, 17, 14, 0, tzinfo=timezone.utc)  # = 08:00 MDT Fri
    wed_8pm = datetime(2026, 4, 16, 2, 0, tzinfo=timezone.utc)   # = 20:00 MDT Wed
    thu_7pm = datetime(2026, 4, 17, 1, 0, tzinfo=timezone.utc)   # = 19:00 MDT Thu

    assert (await get_users_due_for_email(db_session, now=wed_8pm)) == []
    assert (await get_users_due_for_email(db_session, now=thu_7pm)) == []
    assert len(await get_users_due_for_email(db_session, now=thu_8pm)) == 1
    assert len(await get_users_due_for_email(db_session, now=fri_8am)) == 1


@pytest.mark.asyncio
async def test_no_double_send_within_frequency_window(db_session):
    u = User(email="b@x", password_hash="x", full_name="B", is_active=True)
    db_session.add(u)
    await db_session.flush()
    # 20:00 MDT Thu = 02:00 UTC Fri (UTC-6 in April).
    last_sent = datetime(2026, 4, 17, 2, 0, tzinfo=timezone.utc)
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
    # 7 days later — new week's slot (20:00 MDT Thu Apr 23 = 02:00 UTC Fri Apr 24)
    next_thu_8pm = datetime(2026, 4, 24, 2, 0, tzinfo=timezone.utc)
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
    # 20:00 MDT Thu = 02:00 UTC Fri.
    thu_8pm = datetime(2026, 4, 17, 2, 0, tzinfo=timezone.utc)
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
    # 20:00 MDT Thu = 02:00 UTC Fri.
    thu_8pm = datetime(2026, 4, 17, 2, 0, tzinfo=timezone.utc)
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


@pytest.mark.asyncio
async def test_daily_users_not_due_within_24h_of_last_send(db_session):
    u = User(email="d@x", password_hash="x", full_name="D", is_active=True)
    db_session.add(u)
    await db_session.flush()
    # Anchor last_sent at 20:00 MDT Thu = 02:00 UTC Fri so 25h-later lands at
    # 03:00 UTC Sat = 21:00 MDT Fri (gap elapsed, slot fired).
    last = datetime(2026, 4, 17, 2, 0, tzinfo=timezone.utc)
    db_session.add(
        UserEmailPref(
            user_id=u.id,
            is_subscribed=True,
            frequency="daily",
            day_of_week=3,
            time_of_day="20:00",
            last_sent_at=last,
        )
    )
    await db_session.flush()
    # 1 hour later: NOT due (within 24h window)
    assert (
        await get_users_due_for_email(db_session, now=last + timedelta(hours=1))
    ) == []
    # 23 hours later: still NOT due
    assert (
        await get_users_due_for_email(db_session, now=last + timedelta(hours=23))
    ) == []
    # 25 hours later: due (past 24h, slot was today's 20:00)
    assert (
        len(
            await get_users_due_for_email(db_session, now=last + timedelta(hours=25))
        )
        == 1
    )


@pytest.mark.asyncio
async def test_local_time_zone_honored_not_utc(db_session):
    """User sets 20:00 expecting 8pm MT. UTC clock is 6 hours ahead in MDT.
    At 22:00 UTC (= 16:00 MDT) on Thursday, user should NOT be due yet."""
    u = User(email="tz@x", password_hash="x", full_name="TZ", is_active=True)
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

    # Apr 23, 2026 is a Thursday. 22:00 UTC = 16:00 MDT (MDT = UTC-6).
    early_utc = datetime(2026, 4, 23, 22, 0, tzinfo=timezone.utc)
    assert (await get_users_due_for_email(db_session, now=early_utc)) == []

    # 02:30 UTC on Friday = 20:30 MDT Thursday → due
    late_utc = datetime(2026, 4, 24, 2, 30, tzinfo=timezone.utc)
    assert len(await get_users_due_for_email(db_session, now=late_utc)) == 1


@pytest.mark.asyncio
async def test_daily_users_due_every_day_after_slot(db_session):
    """Daily users should not be gated by day_of_week."""
    u = User(email="daily@x", password_hash="x", full_name="D", is_active=True)
    db_session.add(u)
    await db_session.flush()
    db_session.add(
        UserEmailPref(
            user_id=u.id,
            is_subscribed=True,
            frequency="daily",
            day_of_week=3,
            time_of_day="08:00",
            last_sent_at=None,  # Thursday gate would block Mon-Wed
        )
    )
    await db_session.flush()

    # Mon 09:00 MDT = 15:00 UTC — should be due despite day_of_week=3
    mon_local = datetime(2026, 4, 20, 15, 0, tzinfo=timezone.utc)
    assert len(await get_users_due_for_email(db_session, now=mon_local)) == 1

    # Tue 09:00 MDT — should still be due (with last_sent_at None, gap doesn't matter)
    tue_local = datetime(2026, 4, 21, 15, 0, tzinfo=timezone.utc)
    assert len(await get_users_due_for_email(db_session, now=tue_local)) == 1

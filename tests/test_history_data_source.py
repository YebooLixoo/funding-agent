"""Tests for HistoryDataSource protocol + PlatformDBSource adapter."""

from __future__ import annotations

import pytest

from web.services.history_data_source import (
    PlatformDBSource,
    fetch_admin_emailed_opportunities,
)


def test_platformdbsource_returns_rows():
    rows = [
        {
            "composite_id": "x",
            "title": "T",
            "url": "u",
            "deadline": None,
            "summary": "s",
            "funding_amount": None,
            "source": "nsf",
            "source_type": "government",
            "deadline_type": "fixed",
            "opportunity_status": "open",
        }
    ]
    s = PlatformDBSource(rows)
    assert s.get_emailed_opportunities() == rows


def test_platformdbsource_empty():
    assert PlatformDBSource([]).get_emailed_opportunities() == []


@pytest.mark.asyncio
async def test_fetch_admin_emailed_opportunities_filters_by_user(db_session, admin_user):
    """Only deliveries belonging to the admin user are returned."""
    from web.models.user import User
    from web.models.opportunity import Opportunity
    from web.models.user_email_delivery import UserEmailDelivery

    other = User(email="other@x", password_hash="x", full_name="O", is_active=True)
    opp_admin = Opportunity(composite_id="a_1", source="nsf", source_id="1", title="A")
    opp_other = Opportunity(composite_id="o_1", source="nsf", source_id="2", title="O")
    db_session.add_all([other, opp_admin, opp_other])
    await db_session.flush()

    db_session.add(UserEmailDelivery(user_id=admin_user.id, opportunity_id=opp_admin.id))
    db_session.add(UserEmailDelivery(user_id=other.id, opportunity_id=opp_other.id))
    await db_session.flush()

    rows = await fetch_admin_emailed_opportunities(db_session, admin_user.email)
    assert len(rows) == 1
    assert rows[0]["composite_id"] == "a_1"
    assert rows[0]["title"] == "A"

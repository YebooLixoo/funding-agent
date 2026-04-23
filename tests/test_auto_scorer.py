"""Tests for web.services.auto_scorer."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from web.models.opportunity import Opportunity, UserOpportunityScore
from web.models.user import User
from web.services.auto_scorer import score_new_opportunities


@pytest.mark.asyncio
async def test_scores_new_opps_for_each_active_user(db_session):
    u1 = User(email="u1@x", password_hash="x", full_name="U1", is_active=True)
    u2 = User(email="u2@x", password_hash="x", full_name="U2", is_active=True)
    inactive = User(email="i@x", password_hash="x", full_name="I", is_active=False)
    opp = Opportunity(
        composite_id="nsf_X1",
        source="nsf",
        source_id="X1",
        title="Machine Learning Research Grant",
        description="machine learning research opportunity",
    )
    db_session.add_all([u1, u2, inactive, opp])
    await db_session.flush()

    await score_new_opportunities(db_session, [opp.id])

    scores = (await db_session.execute(select(UserOpportunityScore))).scalars().all()
    user_ids = {s.user_id for s in scores}
    assert u1.id in user_ids
    assert u2.id in user_ids
    assert inactive.id not in user_ids


@pytest.mark.asyncio
async def test_empty_opportunity_ids_is_noop(db_session):
    u1 = User(email="u1@x", password_hash="x", full_name="U1", is_active=True)
    db_session.add(u1)
    await db_session.flush()

    await score_new_opportunities(db_session, [])

    scores = (await db_session.execute(select(UserOpportunityScore))).scalars().all()
    assert scores == []

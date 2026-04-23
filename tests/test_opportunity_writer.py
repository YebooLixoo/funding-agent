"""Tests for web.services.opportunity_writer.upsert_opportunity."""

from __future__ import annotations

import pytest

from src.models import Opportunity as OppDC
from web.services.opportunity_writer import upsert_opportunity


@pytest.mark.asyncio
async def test_inserts_new_opportunity(db_session):
    opp = OppDC(source="nsf", source_id="X1", title="T", description="d", url="https://e.com/1")
    row, was_new = await upsert_opportunity(db_session, opp)
    assert was_new is True
    assert row.composite_id == "nsf_X1"


@pytest.mark.asyncio
async def test_dedup_by_composite_id(db_session):
    opp = OppDC(source="nsf", source_id="X1", title="T", description="d", url="https://e.com/1")
    await upsert_opportunity(db_session, opp)
    _, was_new = await upsert_opportunity(db_session, opp)
    assert was_new is False


@pytest.mark.asyncio
async def test_dedup_by_url(db_session):
    a = OppDC(source="nsf", source_id="X1", title="T1", description="d", url="https://same.com")
    b = OppDC(source="nih", source_id="Y1", title="T2", description="d", url="https://same.com")
    await upsert_opportunity(db_session, a)
    _, was_new = await upsert_opportunity(db_session, b)
    assert was_new is False


@pytest.mark.asyncio
async def test_dedup_by_title_similarity(db_session):
    a = OppDC(
        source="nsf",
        source_id="X1",
        title="AI Research Initiative",
        description="d",
        url="https://a.com",
    )
    b = OppDC(
        source="nih",
        source_id="Y1",
        title="Ai research initiative!",
        description="d",
        url="https://b.com",
    )
    await upsert_opportunity(db_session, a)
    _, was_new = await upsert_opportunity(db_session, b)
    assert was_new is False

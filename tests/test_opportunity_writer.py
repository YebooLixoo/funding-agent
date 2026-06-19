"""Tests for web.services.opportunity_writer.upsert_opportunity."""

from __future__ import annotations

import pytest

from src.models import Opportunity as OppDC
from web.models.opportunity import Opportunity as OppRow
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
async def test_dedup_url_tolerates_multiple_existing_rows(db_session):
    """Regression for the 2026-06-18 fetch crash.

    ``Opportunity.url`` is non-unique: two legitimately-distinct rows can share
    one landing-page URL (the two NVIDIA grant tracks did). When a later fetch
    upserts an opp carrying that URL, the URL-dedup query matches >1 row; it must
    treat the opp as an existing duplicate, NOT raise ``MultipleResultsFound``.

    The two same-URL rows are seeded DIRECTLY because ``upsert_opportunity``'s own
    URL-dedup would block the second insert — directly seeding mirrors how the
    live rows were created and is the only way to reach the >1-match state.
    """
    shared = "https://www.nvidia.com/academic-grant-program/"
    db_session.add(OppRow(composite_id="nvidia_sim", source="nvidia",
                          source_id="sim", title="NVIDIA Grant - Simulation", url=shared))
    db_session.add(OppRow(composite_id="nvidia_rob", source="nvidia",
                          source_id="rob", title="NVIDIA Grant - Robotics", url=shared))
    await db_session.flush()

    # Same URL, brand-new composite_id -> URL-dedup query matches BOTH seeded
    # rows. Pre-fix this raised MultipleResultsFound; post-fix it dedups.
    c = OppDC(source="nvidia", source_id="quantum",
              title="Totally Unrelated Program Name Here",
              description="d", url=shared)
    row_c, was_new = await upsert_opportunity(db_session, c)
    assert was_new is False
    assert row_c.url == shared
    assert row_c.composite_id in {"nvidia_sim", "nvidia_rob"}


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

"""Tests for web.services.opportunity_writer.upsert_opportunity."""

from __future__ import annotations

from datetime import datetime, timezone

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


# --- Title dedup must not swallow distinct opportunities --------------------
# Regression for 2026-10-29: the bare >=0.80 title rule (any source, any year)
# merged new fiscal-year cycles and sibling programs into old rows. Replayed on
# all 2026 Grants.gov postings it suppressed 80, of which only 4 were real
# re-posts (identical title AND identical deadline). Titles below are verbatim.

_DL_2026 = datetime(2026, 8, 20, tzinfo=timezone.utc)


def _opp(source: str, source_id: str, title: str, deadline=None) -> OppDC:
    return OppDC(
        source=source,
        source_id=source_id,
        title=title,
        description="d",
        url=f"https://e.com/{source}/{source_id}",
        deadline=deadline,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "old_title, new_title",
    [
        # new fiscal-year cycle
        (
            "Fiscal Year 2024 Flood Mitigation Assistance",
            "Fiscal Year 2026 Flood Mitigation Assistance",
        ),
        (
            "FY 2024 – 2026 Broad Agency Announcement (BAA), Office of Oceanic and "
            "Atmospheric Research (OAR)",
            "FY 2027 - 2029 Broad Agency Announcement (BAA), Oceanic and Atmospheric "
            "Research (OAR)",
        ),
        # sibling programs differing only by region / program name
        (
            "Fiscal Year 2026 Cooperating Technical Partners (CTP) Program - Region 10",
            "Fiscal Year 2026 Cooperating Technical Partners (CTP) Program - Region 9",
        ),
        (
            "Cooperative Agreement for affiliated Partner with the Rocky Mountain "
            "Cooperative Ecosystem Studies Unit",
            "Cooperative Agreement for affiliated Partner with the Desert Southwest "
            "Cooperative Ecosystem Studies Unit",
        ),
        (
            "Fiscal Year 2026 Transit Security Grant Program (TSGP)",
            "Fiscal Year 2026 Port Security Grant Program",
        ),
    ],
)
async def test_same_source_distinct_ids_are_not_title_deduped(db_session, old_title, new_title):
    # Same (known) deadline on purpose: siblings often share one, so the
    # deadline alone must not be what keeps them apart.
    await upsert_opportunity(db_session, _opp("grants_gov", "A", old_title, _DL_2026))
    _, was_new = await upsert_opportunity(
        db_session, _opp("grants_gov", "B", new_title, _DL_2026)
    )
    assert was_new is True


@pytest.mark.asyncio
async def test_new_cycle_with_identical_title_but_new_deadline_is_new(db_session):
    """RESTORE Act CoE: re-issued (GR-RCE-26-001) under the same title, deadline +1yr."""
    title = "RESTORE Act Centers of Excellence Research Grants Program"
    await upsert_opportunity(
        db_session,
        _opp("grants_gov", "A", title, datetime(2026, 10, 31, tzinfo=timezone.utc)),
    )
    _, was_new = await upsert_opportunity(
        db_session,
        _opp("grants_gov", "B", title, datetime(2027, 10, 31, tzinfo=timezone.utc)),
    )
    assert was_new is True


@pytest.mark.asyncio
async def test_repost_with_identical_title_and_deadline_is_duplicate(db_session):
    """An agency re-posting the same NOFO under a new id is still one opportunity."""
    title = "Pax Silica Artificial Intelligence Assistance Project"
    await upsert_opportunity(db_session, _opp("grants_gov", "A", title, _DL_2026))
    _, was_new = await upsert_opportunity(db_session, _opp("grants_gov", "B", title, _DL_2026))
    assert was_new is False


@pytest.mark.asyncio
async def test_curated_refresh_with_bumped_source_id_inserts(db_session):
    """conf/sources/university.yaml: bump source_id (fsgp -> fsgp_fy27) for a new cycle."""
    title = "U of U — Faculty Small Grant Program (FSGP)"
    await upsert_opportunity(db_session, _opp("utah_internal", "fsgp", title))
    _, was_new = await upsert_opportunity(db_session, _opp("utah_internal", "fsgp_fy27", title))
    assert was_new is True


@pytest.mark.asyncio
async def test_cross_source_titles_with_different_numbers_are_distinct(db_session):
    """The 2027 NOFO on Grants.gov is not the curated, year-less YFA awareness row."""
    await upsert_opportunity(
        db_session, _opp("darpa_yfa", "darpa_yfa_b9840aea", "DARPA Young Faculty Award (YFA)")
    )
    _, was_new = await upsert_opportunity(
        db_session, _opp("grants_gov", "B", "Young Faculty Award (YFA) 2027", _DL_2026)
    )
    assert was_new is True


@pytest.mark.asyncio
async def test_cross_source_different_known_deadlines_are_distinct(db_session):
    """Next year's CAREER NOFO must not be swallowed by this year's curated row."""
    title = "Faculty Early Career Development Program (CAREER)"
    await upsert_opportunity(
        db_session,
        _opp("nsf_career", "career", title, datetime(2026, 7, 22, tzinfo=timezone.utc)),
    )
    _, was_new = await upsert_opportunity(
        db_session,
        _opp("grants_gov", "B", title, datetime(2027, 7, 23, tzinfo=timezone.utc)),
    )
    assert was_new is True


@pytest.mark.asyncio
async def test_cross_source_same_deadline_is_still_deduped(db_session):
    title = "Faculty Early Career Development Program (CAREER)"
    await upsert_opportunity(
        db_session,
        _opp("nsf_career", "career", title, datetime(2026, 7, 22, tzinfo=timezone.utc)),
    )
    # Deadline from a different source arrives as a naive date-only datetime.
    _, was_new = await upsert_opportunity(
        db_session, _opp("grants_gov", "B", title, datetime(2026, 7, 22))
    )
    assert was_new is False


@pytest.mark.asyncio
async def test_rescraped_program_with_reworded_title_is_still_deduped(db_session):
    """Scraper ids are a hash of the LLM-written title, so they carry no evidence
    of distinctness: a reworded re-extraction from another subpage is the same
    program and must fall back to fuzzy title matching (review finding)."""
    from src.models import title_derived_source_id

    old_title, new_title = "TACC Startup Project Allocation", "TACC Start-up Project Allocation"
    old = OppDC(
        source="tacc", source_id=title_derived_source_id("tacc", old_title), title=old_title,
        description="d", url="https://tacc.utexas.edu/use-tacc/allocations/",
    )
    new = OppDC(
        source="tacc", source_id=title_derived_source_id("tacc", new_title), title=new_title,
        description="d", url="https://tacc.utexas.edu/use-tacc/allocations/startup/",
    )
    await upsert_opportunity(db_session, old)
    _, was_new = await upsert_opportunity(db_session, new)
    assert was_new is False


@pytest.mark.asyncio
async def test_cross_source_number_check_ignores_dash_style(db_session):
    """'FY 2024-2026' and 'FY 2024 – 2026' carry the same numbers (review finding)."""
    await upsert_opportunity(
        db_session,
        _opp("grants_gov", "A", "FY 2024 – 2026 Broad Agency Announcement (BAA), OAR", _DL_2026),
    )
    _, was_new = await upsert_opportunity(
        db_session,
        _opp("noaa", "B", "FY 2024-2026 Broad Agency Announcement (BAA), OAR", _DL_2026),
    )
    assert was_new is False


@pytest.mark.asyncio
async def test_stores_agency(db_session):
    opp = OppDC(source="grants_gov", source_id="A1", title="T", description="d",
                url="https://e.com/a1", agency="DOT-FHWA")
    row, _ = await upsert_opportunity(db_session, opp)
    assert row.agency == "DOT-FHWA"

"""Pipeline stages must carry every Opportunity field through untouched.

The keyword filter, LLM filter and summarizer each return new Opportunity
instances. Hand-copied constructors silently dropped fields added later
(``agency`` never reached the DB after April 2026), so these tests compare the
whole dataclass, not individual fields.
"""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.filter.keyword_filter import FilterConfig, KeywordFilter
from src.filter.llm_filter import LLMFilter
from src.models import Opportunity
from src.summarizer import Summarizer


def _fully_populated_opp() -> Opportunity:
    """An opportunity with every field set, so a dropped field shows up as a diff."""
    opp = Opportunity(
        source="grants_gov",
        source_id="abc-123",
        title="Machine learning for transportation safety",
        description="Machine learning research for transportation systems.",
        url="https://example.com/abc-123",
        source_type="compute",
        deadline=datetime(2027, 1, 15, tzinfo=timezone.utc),
        posted_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
        funding_amount="$500,000",
        keywords=["ai"],
        relevance_score=0.01,
        summary="original summary",
        opportunity_status="coming_soon",
        deadline_type="rolling",
        resource_type="gpu",
        resource_provider="NSF ACCESS",
        resource_scale="large",
        allocation_details="Up to 1,000 GPU-hours",
        eligibility="Faculty PI",
        access_url="https://example.com/apply",
        agency="DOT-FHWA",
    )
    unset = [
        f.name for f in fields(opp)
        if getattr(opp, f.name) in (None, "", []) or getattr(opp, f.name) == f.default
    ]
    assert not unset, f"give these new fields a non-default value here: {unset}"
    return opp


def test_keyword_filter_preserves_every_field():
    opp = _fully_populated_opp()
    kw = KeywordFilter(FilterConfig(
        primary_keywords=["machine learning"],
        domain_keywords=["transportation"],
        exclusions=[],
    ))
    accepted, borderline = kw.filter([opp])
    [out] = accepted + borderline
    assert out.relevance_score == kw.score(opp)
    assert out == replace(opp, relevance_score=out.relevance_score)


@pytest.mark.asyncio
async def test_llm_filter_preserves_every_field(monkeypatch):
    opp = _fully_populated_opp()
    llm = LLMFilter()
    monkeypatch.setattr(llm, "evaluate", AsyncMock(return_value=(0.9, "relevant")))
    [out] = await llm.filter_borderline([opp], threshold=0.5)
    assert out == replace(opp, relevance_score=0.9, summary="relevant")


@pytest.mark.asyncio
async def test_summarizer_preserves_every_field(monkeypatch):
    opp = _fully_populated_opp()
    summarizer = Summarizer()
    monkeypatch.setattr(summarizer, "summarize", AsyncMock(return_value="new summary"))
    [out] = await summarizer.summarize_batch([opp])
    assert out == replace(opp, summary="new summary")

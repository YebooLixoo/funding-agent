"""Tests for relevance filter modules."""

from __future__ import annotations

import pytest

from src.filter.keyword_filter import FilterConfig, KeywordFilter
from src.models import Opportunity


def _make_opp(title: str, description: str = "") -> Opportunity:
    return Opportunity(
        source="test",
        source_id="1",
        title=title,
        description=description,
        url="https://example.com",
    )


@pytest.fixture
def kw_filter() -> KeywordFilter:
    config = FilterConfig(
        primary_keywords=["artificial intelligence", "machine learning", "deep learning"],
        domain_keywords=["transportation", "vehicle", "traffic", "infrastructure"],
        exclusions=["K-12", "undergraduate only"],
        keyword_threshold=0.3,
    )
    return KeywordFilter(config)


class TestKeywordFilter:
    def test_high_relevance(self, kw_filter: KeywordFilter):
        opp = _make_opp(
            "Machine Learning for Autonomous Vehicle Traffic Management",
            "Deep learning approaches for intelligent transportation systems.",
        )
        score = kw_filter.score(opp)
        assert score >= 0.6

    def test_ai_only(self, kw_filter: KeywordFilter):
        opp = _make_opp(
            "Deep Learning for Medical Imaging",
            "Novel neural network architectures for radiology.",
        )
        score = kw_filter.score(opp)
        assert 0.3 <= score < 0.8

    def test_no_relevance(self, kw_filter: KeywordFilter):
        opp = _make_opp(
            "Office Furniture Procurement",
            "Federal procurement for office supplies and furniture.",
        )
        score = kw_filter.score(opp)
        assert score < 0.3

    def test_exclusion(self, kw_filter: KeywordFilter):
        opp = _make_opp(
            "K-12 AI Education Program",
            "Teaching artificial intelligence in K-12 schools.",
        )
        score = kw_filter.score(opp)
        assert score == 0.0

    def test_filter_splits_correctly(self, kw_filter: KeywordFilter):
        opps = [
            _make_opp("Machine Learning for Traffic Prediction", "Deep learning transportation"),
            _make_opp("Office Supplies", "Paperwork"),
            _make_opp("AI Research Grant", "Artificial intelligence research funding"),
        ]
        accepted, borderline = kw_filter.filter(opps)
        assert len(accepted) >= 1
        total_filtered = len(accepted) + len(borderline)
        assert total_filtered <= len(opps)

    def test_extract_keywords(self, kw_filter: KeywordFilter):
        opp = _make_opp("Machine Learning for Transportation Infrastructure")
        keywords = kw_filter.extract_matching_keywords(opp)
        assert "machine learning" in keywords
        assert "transportation" in keywords
        assert "infrastructure" in keywords

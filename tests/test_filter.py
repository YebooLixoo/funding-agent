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
        primary_keywords=[
            "artificial intelligence", "machine learning", "deep learning",
            "autonomous", "data science",
        ],
        domain_keywords=[
            "transportation", "vehicle", "traffic", "infrastructure",
            "self-driving", "connected vehicle", "V2X", "civil engineering",
            "network resilience", "optimization", "operations research",
            "structural engineering", "evacuation", "flood",
        ],
        exclusions=["K-12", "undergraduate only"],
        career_keywords=[
            "early career", "CAREER", "young investigator", "early-career",
            "assistant professor", "Faculty Early Career",
        ],
        faculty_keywords=[
            "faculty", "principal investigator", "professor", "university",
        ],
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
            "Deep Learning for Optimization",
            "Novel neural network architectures for combinatorial optimization.",
        )
        score = kw_filter.score(opp)
        assert 0.3 <= score < 0.8

    def test_health_without_engineering_rejected(self, kw_filter: KeywordFilter):
        """Health/medical AI without civil/environmental context is rejected."""
        opp = _make_opp(
            "Deep Learning for Medical Imaging",
            "Novel neural network architectures for radiology.",
        )
        score = kw_filter.score(opp)
        assert score == 0.0

    def test_health_with_engineering_accepted(self, kw_filter: KeywordFilter):
        """Health topic WITH civil/environmental context is accepted."""
        opp = _make_opp(
            "AI for Public Health and Air Quality Monitoring",
            "Machine learning for environmental health monitoring in transportation corridors and infrastructure.",
        )
        score = kw_filter.score(opp)
        assert score > 0.0

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

    # --- New tests for multi-track scoring ---

    def test_career_only_scoring(self, kw_filter: KeywordFilter):
        """NSF CAREER Award with faculty keywords should score via Track 2."""
        opp = _make_opp(
            "NSF Faculty Early Career Development Program (CAREER)",
            "Supports early career faculty at universities as principal investigators.",
        )
        score = kw_filter.score(opp)
        # Track 2: career matches (CAREER, early career, Faculty Early Career) + faculty matches
        assert score >= 0.3

    def test_career_plus_domain_cross_bonus(self, kw_filter: KeywordFilter):
        """Early career + domain keywords should get cross-bonus."""
        opp = _make_opp(
            "Early Career Award in Civil Engineering",
            "Young investigator program for infrastructure resilience research.",
        )
        score = kw_filter.score(opp)
        # Track 2 career score + cross-bonus for career+domain
        assert score >= 0.5

    def test_career_plus_primary_cross_bonus(self, kw_filter: KeywordFilter):
        """Career + AI keywords should get the +0.2 cross-bonus."""
        opp = _make_opp(
            "Early Career Award in Machine Learning",
            "Young investigator program for artificial intelligence researchers at university.",
        )
        score = kw_filter.score(opp)
        # Track 1 AI score + cross-bonus for career+primary
        assert score >= 0.6

    def test_civil_engineering_borderline(self, kw_filter: KeywordFilter):
        """Civil engineering without AI should score borderline via domain."""
        opp = _make_opp(
            "Civil Engineering Infrastructure Grant",
            "Structural engineering for flood resilience and evacuation planning.",
        )
        score = kw_filter.score(opp)
        # Domain matches only, no primary/career → borderline
        assert 0.3 <= score <= 0.6

    def test_synonym_self_driving(self, kw_filter: KeywordFilter):
        """Synonym 'self-driving' should match just like 'autonomous'."""
        opp = _make_opp(
            "Self-Driving Car Research Grant",
            "Data science for connected vehicle and V2X systems.",
        )
        score = kw_filter.score(opp)
        # primary: data science; domain: self-driving, connected vehicle, V2X
        assert score >= 0.6

    def test_operations_research_borderline(self, kw_filter: KeywordFilter):
        """Operations research / optimization should score via domain keywords."""
        opp = _make_opp(
            "Network Optimization and Operations Research",
            "Optimization methods for logistics and scheduling problems.",
        )
        score = kw_filter.score(opp)
        # Domain matches: optimization, operations research → 0.4
        assert score >= 0.3

    def test_irrelevant_rejection(self, kw_filter: KeywordFilter):
        """Completely unrelated opportunity should score 0."""
        opp = _make_opp(
            "Marine Biology Field Station Renovation",
            "Upgrade laboratory facilities for coral reef studies.",
        )
        score = kw_filter.score(opp)
        assert score == 0.0

    def test_extract_career_faculty_keywords(self, kw_filter: KeywordFilter):
        """extract_matching_keywords should include career and faculty keywords."""
        opp = _make_opp(
            "CAREER Award for Faculty in Machine Learning",
            "University professor early career program.",
        )
        keywords = kw_filter.extract_matching_keywords(opp)
        assert "machine learning" in keywords
        assert "CAREER" in keywords
        assert "faculty" in keywords

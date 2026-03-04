"""Tests for fetcher modules."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.fetcher import FETCHER_REGISTRY, get_fetcher
from src.fetcher.web_scraper import WebScraperFetcher
from src.models import Opportunity


class TestFetcherRegistry:
    def test_all_fetchers_registered(self):
        expected = {"sam_gov", "nsf", "grants_gov", "web_scraper"}
        assert expected == set(FETCHER_REGISTRY.keys())

    def test_get_fetcher_valid(self):
        fetcher = get_fetcher("nsf")
        assert fetcher.source_name == "nsf"

    def test_get_fetcher_invalid(self):
        with pytest.raises(ValueError, match="Unknown fetcher"):
            get_fetcher("nonexistent")


class TestWebScraper:
    def test_extract_funding_pattern(self):
        scraper = WebScraperFetcher()
        text = (
            "Call for Proposals: AI in Transportation\n"
            "We invite researchers to submit proposals for AI-driven traffic management.\n"
            "Funding: $500,000 per project. Deadline: March 15, 2026.\n"
            "Applications due by the deadline above."
        )
        opps = scraper._extract_opportunities("test", "Test Source", "https://example.com", text)
        assert len(opps) >= 1
        assert opps[0].source == "test"

    def test_extract_no_funding_keywords(self):
        scraper = WebScraperFetcher()
        text = "This is a generic page about our company history and products."
        opps = scraper._extract_opportunities("test", "Test", "https://example.com", text)
        assert len(opps) == 0


class TestOpportunityModel:
    def test_composite_id(self):
        opp = Opportunity(
            source="sam_gov",
            source_id="12345",
            title="Test",
            description="Test desc",
            url="https://example.com",
        )
        assert opp.composite_id == "sam_gov_12345"

    def test_frozen(self):
        opp = Opportunity(
            source="nsf",
            source_id="99",
            title="Test",
            description="Desc",
            url="https://example.com",
        )
        with pytest.raises(AttributeError):
            opp.title = "Modified"

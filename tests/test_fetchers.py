"""Tests for fetcher modules."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.fetcher import FETCHER_REGISTRY, get_fetcher
from src.fetcher.opportunity_validator import OpportunityValidator
from src.fetcher.web_scraper import WebScraperFetcher
from src.models import Opportunity


class TestFetcherRegistry:
    def test_all_fetchers_registered(self):
        expected = {"nsf", "grants_gov", "web_scraper"}
        assert expected == set(FETCHER_REGISTRY.keys())

    def test_get_fetcher_valid(self):
        fetcher = get_fetcher("nsf")
        assert fetcher.source_name == "nsf"

    def test_get_fetcher_invalid(self):
        with pytest.raises(ValueError, match="Unknown fetcher"):
            get_fetcher("nonexistent")


class TestWebScraper:
    def test_scraper_has_validator(self):
        scraper = WebScraperFetcher()
        assert isinstance(scraper.validator, OpportunityValidator)

    def test_scraper_accepts_model_param(self):
        scraper = WebScraperFetcher(model="gpt-5.2")
        assert scraper.validator.model == "gpt-5.2"


class TestOpportunityValidator:
    def test_init_default_model(self):
        validator = OpportunityValidator()
        assert validator.model == "gpt-5.2"

    def test_init_custom_model(self):
        validator = OpportunityValidator(model="gpt-4o")
        assert validator.model == "gpt-4o"

    def test_parse_page_response_valid(self):
        validator = OpportunityValidator()
        raw = json.dumps([
            {
                "title": "AI Research Grant",
                "description": "Funding for AI research",
                "deadline": "2027-06-15",
                "funding_amount": "$50K",
                "confidence": 0.9,
            }
        ])
        opps = validator._parse_page_response(raw, "https://example.com", "test")
        assert len(opps) == 1
        assert opps[0].title == "AI Research Grant"
        assert opps[0].source == "test"
        assert opps[0].funding_amount == "$50K"

    def test_parse_page_response_low_confidence(self):
        validator = OpportunityValidator()
        raw = json.dumps([
            {
                "title": "Maybe a grant",
                "description": "Unclear",
                "deadline": "2027-06-15",
                "confidence": 0.3,
            }
        ])
        opps = validator._parse_page_response(raw, "https://example.com", "test")
        assert len(opps) == 0

    def test_parse_page_response_past_deadline(self):
        validator = OpportunityValidator()
        raw = json.dumps([
            {
                "title": "Expired Grant",
                "description": "Already closed",
                "deadline": "2020-01-01",
                "confidence": 0.9,
            }
        ])
        opps = validator._parse_page_response(raw, "https://example.com", "test")
        assert len(opps) == 0

    def test_parse_page_response_empty(self):
        validator = OpportunityValidator()
        raw = "[]"
        opps = validator._parse_page_response(raw, "https://example.com", "test")
        assert len(opps) == 0

    def test_parse_page_response_markdown_fenced(self):
        validator = OpportunityValidator()
        raw = '```json\n[{"title": "Grant", "description": "Desc", "deadline": "2027-12-01", "confidence": 0.8}]\n```'
        opps = validator._parse_page_response(raw, "https://example.com", "test")
        assert len(opps) == 1

    def test_parse_page_response_invalid_json(self):
        validator = OpportunityValidator()
        raw = "This is not JSON"
        opps = validator._parse_page_response(raw, "https://example.com", "test")
        assert len(opps) == 0

    def test_parse_item_response_valid(self):
        validator = OpportunityValidator()
        raw = json.dumps({"is_valid": True, "confidence": 0.9, "reason": "Real grant"})
        is_valid, confidence, reason = validator._parse_item_response(raw)
        assert is_valid is True
        assert confidence == 0.9
        assert reason == "Real grant"

    def test_parse_item_response_invalid(self):
        validator = OpportunityValidator()
        raw = json.dumps({"is_valid": False, "confidence": 0.2, "reason": "Job posting"})
        is_valid, confidence, reason = validator._parse_item_response(raw)
        assert is_valid is False
        assert confidence == 0.2

    def test_parse_item_response_bad_json(self):
        validator = OpportunityValidator()
        raw = "not json"
        is_valid, confidence, reason = validator._parse_item_response(raw)
        assert is_valid is True  # defaults to accepting
        assert confidence == 0.5

    def test_validate_page_content_no_client(self):
        validator = OpportunityValidator()
        # Without OpenAI configured, should return empty
        with patch.object(validator, "_get_client", return_value=None):
            result = validator.validate_page_content("text", "url", "label", "src")
            assert result == []

    def test_validate_opportunity_no_client(self):
        validator = OpportunityValidator()
        with patch.object(validator, "_get_client", return_value=None):
            is_valid, confidence, reason = validator.validate_opportunity(
                "Title", "Desc", None, "url"
            )
            assert is_valid is True
            assert confidence == 0.5


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

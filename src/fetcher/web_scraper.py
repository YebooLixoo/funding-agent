"""Generic web scraper for funding pages with landing page detection."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.fetcher import register_fetcher
from src.fetcher.base import BaseFetcher
from src.fetcher.opportunity_validator import OpportunityValidator
from src.models import Opportunity

logger = logging.getLogger(__name__)


@register_fetcher("web_scraper")
class WebScraperFetcher(BaseFetcher):
    """Generic scraper for funding pages with two-phase landing page support.

    Phase 1: Fetch page, classify as opportunity_page or landing_page.
    Phase 2: If landing_page, follow discovered funding links to subpages.
    """

    source_name = "web_scraper"
    source_type = "industry"

    # Content hashes from previous runs (in-memory cache per session)
    _content_hashes: dict[str, str] = {}

    def __init__(self, model: str = "gpt-5.2", source_type: str = "industry", **kwargs) -> None:
        super().__init__(**kwargs)
        self.source_type = source_type
        self.validator = OpportunityValidator(model=model)

    async def fetch(
        self,
        window_start: datetime,
        window_end: datetime,
        keywords: Optional[list[str]] = None,
    ) -> list[Opportunity]:
        return []

    async def fetch_source(
        self,
        name: str,
        label: str,
        url: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[Opportunity]:
        """Fetch opportunities from a single source with landing page detection.

        Args:
            name: Source identifier (e.g., 'nvidia').
            label: Human-readable label.
            url: URL to scrape.
            window_start: Start of fetch window.
            window_end: End of fetch window.

        Returns:
            List of validated opportunities found.
        """
        try:
            resp = await self._get(url)
            html = resp.text
        except Exception:
            logger.exception(f"Failed to fetch {label} ({url})")
            return []

        # Check for content changes via hash
        content_hash = hashlib.sha256(html.encode()).hexdigest()[:16]
        previous_hash = self._content_hashes.get(name)
        self._content_hashes[name] = content_hash

        if previous_hash and previous_hash == content_hash:
            logger.debug(f"{label}: no content change detected")
            return []

        soup = BeautifulSoup(html, "lxml")

        # Phase 1: Extract links before stripping navigation
        links = self._extract_links(soup, url)

        # Remove script, style, nav, footer elements for text extraction
        for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)

        # Phase 1: Classify page and extract opportunities/funding links
        page_type, opportunities, funding_links = self.validator.classify_and_extract(
            text=text,
            url=url,
            label=label,
            links=links,
            source_name=name,
            source_type=self.source_type,
        )

        if page_type == "opportunity_page":
            logger.info(f"{label}: opportunity page, found {len(opportunities)} opportunities")
            return opportunities

        if page_type == "irrelevant":
            logger.info(f"{label}: classified as irrelevant, skipping")
            return opportunities

        # Phase 2: Landing page — follow discovered funding links
        logger.info(f"{label}: landing page, following {len(funding_links)} funding links")
        for link_url, link_label in funding_links:
            try:
                sub_opps = await self._fetch_subpage(link_url, link_label, name)
                opportunities.extend(sub_opps)
            except Exception:
                logger.debug(f"Failed to fetch subpage: {link_url}")

        logger.info(f"{label}: found {len(opportunities)} total opportunities")
        return opportunities

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        """Extract all links with anchor text from the page."""
        links = []
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            text = a.get_text(strip=True)
            if text and href.startswith("http"):
                links.append({"url": href, "text": text})
        return links

    async def _fetch_subpage(
        self, url: str, label: str, source_name: str
    ) -> list[Opportunity]:
        """Fetch and validate a specific funding opportunity subpage."""
        resp = await self._get(url)
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)

        return self.validator.validate_page_content(
            text=text,
            url=url,
            label=label,
            source_name=source_name,
            source_type=self.source_type,
        )

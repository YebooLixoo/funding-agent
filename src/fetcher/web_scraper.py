"""Generic industry web scraper for funding pages."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from src.fetcher import register_fetcher
from src.fetcher.base import BaseFetcher
from src.fetcher.opportunity_validator import OpportunityValidator
from src.models import Opportunity

logger = logging.getLogger(__name__)


@register_fetcher("web_scraper")
class WebScraperFetcher(BaseFetcher):
    """Generic scraper for industry funding pages.

    Fetches page HTML, extracts text, detects changes via content hashing,
    and uses LLM to validate real funding opportunities.
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
        # This is called per-source from the pipeline; override source_name per call
        return []

    async def fetch_source(
        self,
        name: str,
        label: str,
        url: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[Opportunity]:
        """Fetch opportunities from a single industry source.

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

        # Remove script, style, nav, footer elements
        for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        # Use LLM validator to identify real opportunities
        opportunities = self.validator.validate_page_content(
            text=text,
            url=url,
            label=label,
            source_name=name,
            source_type=self.source_type,
        )

        logger.info(f"{label}: found {len(opportunities)} validated opportunities")
        return opportunities

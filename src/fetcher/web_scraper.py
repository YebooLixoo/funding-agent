"""Generic industry web scraper for funding pages."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from src.fetcher import register_fetcher
from src.fetcher.base import BaseFetcher
from src.models import Opportunity
from src.utils import parse_date

logger = logging.getLogger(__name__)


@register_fetcher("web_scraper")
class WebScraperFetcher(BaseFetcher):
    """Generic scraper for industry funding pages.

    Fetches page HTML, extracts text, detects changes via content hashing,
    and parses for funding-related information.
    """

    source_name = "web_scraper"
    source_type = "industry"

    # Content hashes from previous runs (in-memory cache per session)
    _content_hashes: dict[str, str] = {}

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
            List of opportunities found.
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

        # Extract potential opportunities from the page
        opportunities = self._extract_opportunities(name, label, url, text)

        if not opportunities:
            # Create a single opportunity representing the page content
            opp = Opportunity(
                source=name,
                source_id=f"{name}_{content_hash}",
                title=f"{label} - Page Update Detected",
                description=text[:2000],
                url=url,
                source_type="industry",
                posted_date=datetime.utcnow(),
            )
            opportunities = [opp]

        logger.info(f"{label}: found {len(opportunities)} potential opportunities")
        return opportunities

    def _extract_opportunities(
        self, source: str, label: str, base_url: str, text: str
    ) -> list[Opportunity]:
        """Extract individual opportunities from page text.

        Looks for patterns like:
        - "Call for proposals", "Request for applications"
        - Deadline mentions
        - Funding amount mentions
        """
        opportunities = []

        # Split text into sections by common headings
        sections = re.split(
            r'\n(?=[A-Z][^a-z]*(?:Grant|Award|Fellowship|Call|Program|Fund|Opportunity))',
            text,
        )

        funding_pattern = re.compile(
            r'(?:grant|award|fellowship|funding|call for|request for|RFP|RFA|opportunity)',
            re.IGNORECASE,
        )
        deadline_pattern = re.compile(
            r'(?:deadline|due date|closes?|submit by|applications? due)[:\s]*'
            r'(\w+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})',
            re.IGNORECASE,
        )
        amount_pattern = re.compile(
            r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:K|M|million|thousand))?',
            re.IGNORECASE,
        )

        for section in sections:
            if len(section.strip()) < 50:
                continue
            if not funding_pattern.search(section):
                continue

            # Extract title (first line of section)
            lines = section.strip().split("\n")
            title = lines[0][:200].strip()

            # Extract deadline
            deadline = None
            deadline_match = deadline_pattern.search(section)
            if deadline_match:
                deadline = parse_date(deadline_match.group(1))

            # Extract funding amount
            amount = None
            amount_match = amount_pattern.search(section)
            if amount_match:
                amount = amount_match.group(0)

            section_hash = hashlib.md5(section.encode()).hexdigest()[:8]
            opp = Opportunity(
                source=source,
                source_id=f"{source}_{section_hash}",
                title=f"{label}: {title}",
                description=section[:2000],
                url=base_url,
                source_type="industry",
                deadline=deadline,
                funding_amount=amount,
                posted_date=datetime.utcnow(),
            )
            opportunities.append(opp)

        return opportunities

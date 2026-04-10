"""NSF RSS feed fetcher for funding opportunity announcements."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import feedparser

from src.fetcher import register_fetcher
from src.fetcher.base import BaseFetcher
from src.fetcher.opportunity_validator import OpportunityValidator
from src.models import Opportunity
from src.utils import parse_date

logger = logging.getLogger(__name__)

_RSS_URL = "https://www.nsf.gov/rss/rss_www_funding.xml"


@register_fetcher("nsf")
class NSFFetcher(BaseFetcher):
    """Fetch from NSF RSS funding feed.

    Uses the RSS feed for new funding opportunity announcements.
    Each item is validated via LLM to confirm it's a real, open call.
    """

    source_name = "nsf"
    source_type = "government"

    def __init__(self, model: str = "gpt-5.2", **kwargs) -> None:
        super().__init__(**kwargs)
        self.validator = OpportunityValidator(model=model)

    async def fetch(
        self,
        window_start: Optional[datetime],
        window_end: datetime,
        keywords: Optional[list[str]] = None,
    ) -> list[Opportunity]:
        results: list[Opportunity] = []

        try:
            rss_opps = await self._fetch_rss(window_start, window_end)
            results.extend(rss_opps)
        except Exception:
            logger.exception("NSF RSS fetch failed")

        logger.info(f"NSF: fetched {len(results)} validated opportunities")
        return results

    async def _fetch_rss(
        self, window_start: Optional[datetime], window_end: datetime
    ) -> list[Opportunity]:
        """Parse NSF funding RSS feed for new announcements."""
        resp = await self._get(_RSS_URL)
        feed = feedparser.parse(resp.text)

        opportunities = []
        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            # Filter by time window (window_start=None means no lower bound / bootstrap)
            if published:
                if window_start is not None and published < window_start:
                    continue
                if published > window_end:
                    continue

            title = entry.get("title", "")
            description = entry.get("summary", "")
            url = entry.get("link", "")

            # Validate via LLM
            is_valid, confidence, reason = self.validator.validate_opportunity(
                title=title,
                description=description,
                deadline=None,
                url=url,
            )

            if not is_valid or confidence < 0.5:
                logger.debug(f"NSF RSS rejected: {title[:60]} ({reason})")
                continue

            opp = Opportunity(
                source=self.source_name,
                source_id=f"rss_{hash(url) % 10**8}",
                title=title,
                description=description,
                url=url,
                source_type=self.source_type,
                posted_date=published,
            )
            opportunities.append(opp)

        return opportunities

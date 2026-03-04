"""NSF Awards API + RSS feed fetcher."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

import feedparser

from src.fetcher import register_fetcher
from src.fetcher.base import BaseFetcher
from src.models import Opportunity
from src.utils import parse_date

logger = logging.getLogger(__name__)

_API_URL = "http://api.nsf.gov/services/v1/awards.json"
_RSS_URL = "https://www.nsf.gov/rss/rss_www_funding.xml"


@register_fetcher("nsf")
class NSFFetcher(BaseFetcher):
    """Fetch from NSF Awards API and RSS funding feed.

    Dual approach:
    - Awards API: keyword search for recent awards (indicates funded topics)
    - RSS feed: new funding opportunity announcements
    """

    source_name = "nsf"
    source_type = "government"

    async def fetch(
        self,
        window_start: datetime,
        window_end: datetime,
        keywords: Optional[list[str]] = None,
    ) -> list[Opportunity]:
        keywords = keywords or ["artificial intelligence", "machine learning"]
        results: list[Opportunity] = []
        seen_ids: set[str] = set()

        # 1. Awards API search
        for kw in keywords[:3]:
            try:
                opps = await self._search_awards(kw, window_start, window_end)
                for opp in opps:
                    if opp.source_id not in seen_ids:
                        seen_ids.add(opp.source_id)
                        results.append(opp)
            except Exception:
                logger.exception(f"NSF awards search failed for: {kw}")

        # 2. RSS feed
        try:
            rss_opps = await self._fetch_rss(window_start, window_end)
            for opp in rss_opps:
                if opp.source_id not in seen_ids:
                    seen_ids.add(opp.source_id)
                    results.append(opp)
        except Exception:
            logger.exception("NSF RSS fetch failed")

        logger.info(f"NSF: fetched {len(results)} opportunities")
        return results

    async def _search_awards(
        self, keyword: str, window_start: datetime, window_end: datetime
    ) -> list[Opportunity]:
        params = {
            "keyword": keyword,
            "dateStart": window_start.strftime("%m/%d/%Y"),
            "dateEnd": window_end.strftime("%m/%d/%Y"),
            "printFields": "id,title,abstractText,startDate,expDate,fundsObligatedAmt,fundProgramName",
            "offset": 1,
            "rpp": 50,
        }

        resp = await self._get(_API_URL, params=params)
        data = resp.json()

        opportunities = []
        for award in data.get("response", {}).get("award", []):
            opp = Opportunity(
                source=self.source_name,
                source_id=str(award.get("id", "")),
                title=award.get("title", ""),
                description=award.get("abstractText", ""),
                url=f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={award.get('id', '')}",
                source_type=self.source_type,
                posted_date=parse_date(award.get("startDate", "")),
                deadline=parse_date(award.get("expDate", "")),
                funding_amount=f"${award['fundsObligatedAmt']:,.0f}" if award.get("fundsObligatedAmt") else None,
            )
            opportunities.append(opp)

        return opportunities

    async def _fetch_rss(
        self, window_start: datetime, window_end: datetime
    ) -> list[Opportunity]:
        """Parse NSF funding RSS feed for new announcements."""
        resp = await self._get(_RSS_URL)
        feed = feedparser.parse(resp.text)

        opportunities = []
        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])

            # Filter by time window
            if published and (published < window_start or published > window_end):
                continue

            opp = Opportunity(
                source=self.source_name,
                source_id=f"rss_{hash(entry.get('link', '')) % 10**8}",
                title=entry.get("title", ""),
                description=entry.get("summary", ""),
                url=entry.get("link", ""),
                source_type=self.source_type,
                posted_date=published,
            )
            opportunities.append(opp)

        return opportunities

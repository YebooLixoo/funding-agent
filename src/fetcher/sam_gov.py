"""SAM.gov Opportunities API fetcher."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from src.fetcher import register_fetcher
from src.fetcher.base import BaseFetcher
from src.models import Opportunity
from src.utils import parse_date

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.sam.gov/opportunities/v2/search"


@register_fetcher("sam_gov")
class SAMGovFetcher(BaseFetcher):
    """Fetch funding opportunities from SAM.gov.

    Rate limit: 10 requests/day. We use 1 request per keyword per fetch.
    """

    source_name = "sam_gov"
    source_type = "government"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.api_key = os.environ.get("SAM_GOV_API_KEY", "")

    async def fetch(
        self,
        window_start: datetime,
        window_end: datetime,
        keywords: Optional[list[str]] = None,
    ) -> list[Opportunity]:
        if not self.api_key:
            logger.warning("SAM_GOV_API_KEY not set, skipping SAM.gov fetch")
            return []

        keywords = keywords or ["artificial intelligence transportation"]
        results: list[Opportunity] = []
        seen_ids: set[str] = set()

        for kw in keywords[:3]:  # Limit to 3 keywords to stay within rate limit
            try:
                opps = await self._search(kw, window_start, window_end)
                for opp in opps:
                    if opp.source_id not in seen_ids:
                        seen_ids.add(opp.source_id)
                        results.append(opp)
            except Exception:
                logger.exception(f"SAM.gov search failed for keyword: {kw}")

        logger.info(f"SAM.gov: fetched {len(results)} opportunities")
        return results

    async def _search(
        self, keyword: str, window_start: datetime, window_end: datetime
    ) -> list[Opportunity]:
        params = {
            "api_key": self.api_key,
            "postedFrom": window_start.strftime("%m/%d/%Y"),
            "postedTo": window_end.strftime("%m/%d/%Y"),
            "keywords": keyword,
            "ptype": "o,p,k",  # Opportunities, presolicitation, special notice
            "limit": 100,
        }

        resp = await self._get(_BASE_URL, params=params)
        data = resp.json()

        opportunities = []
        for item in data.get("opportunitiesData", []):
            opp = Opportunity(
                source=self.source_name,
                source_id=str(item.get("noticeId", "")),
                title=item.get("title", ""),
                description=item.get("description", item.get("title", "")),
                url=f"https://sam.gov/opp/{item.get('noticeId', '')}",
                source_type=self.source_type,
                deadline=parse_date(item.get("responseDeadLine", "")),
                posted_date=parse_date(item.get("postedDate", "")),
                funding_amount=item.get("award", {}).get("amount") if item.get("award") else None,
            )
            opportunities.append(opp)

        return opportunities

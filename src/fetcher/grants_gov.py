"""Grants.gov Simpler API fetcher."""

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

_BASE_URL = "https://api.simpler.grants.gov/v1/opportunities/search"


@register_fetcher("grants_gov")
class GrantsGovFetcher(BaseFetcher):
    """Fetch from Grants.gov Simpler API.

    Rate limit: 60 requests/minute.
    Uses POST with JSON body for search.
    """

    source_name = "grants_gov"
    source_type = "government"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.api_key = os.environ.get("GRANTS_GOV_API_KEY", "")

    async def fetch(
        self,
        window_start: datetime,
        window_end: datetime,
        keywords: Optional[list[str]] = None,
    ) -> list[Opportunity]:
        if not self.api_key:
            logger.warning("GRANTS_GOV_API_KEY not set, skipping Grants.gov fetch")
            return []

        keywords = keywords or [
            "artificial intelligence AND transportation",
            "machine learning AND infrastructure",
        ]
        results: list[Opportunity] = []
        seen_ids: set[str] = set()

        for kw in keywords:
            try:
                opps = await self._search(kw, window_start, window_end)
                for opp in opps:
                    if opp.source_id not in seen_ids:
                        seen_ids.add(opp.source_id)
                        results.append(opp)
            except Exception:
                logger.exception(f"Grants.gov search failed for: {kw}")

        logger.info(f"Grants.gov: fetched {len(results)} opportunities")
        return results

    async def _search(
        self, query: str, window_start: datetime, window_end: datetime, page: int = 1
    ) -> list[Opportunity]:
        headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

        body = {
            "query": query,
            "filters": {
                "post_date": {
                    "start_date": window_start.strftime("%Y-%m-%d"),
                    "end_date": window_end.strftime("%Y-%m-%d"),
                },
                "opportunity_status": {
                    "one_of": ["posted", "forecasted"],
                },
            },
            "pagination": {
                "page_offset": page,
                "page_size": 25,
                "sort_order": [
                    {
                        "order_by": "post_date",
                        "sort_direction": "descending",
                    }
                ],
            },
        }

        resp = await self._post(_BASE_URL, json=body, headers=headers)
        data = resp.json()

        opportunities = []
        for item in data.get("data", []):
            opp = Opportunity(
                source=self.source_name,
                source_id=str(item.get("opportunity_id", "")),
                title=item.get("opportunity_title", ""),
                description=item.get("summary", {}).get("summary_description", "")
                    if isinstance(item.get("summary"), dict) else "",
                url=f"https://simpler.grants.gov/opportunity/{item.get('opportunity_id', '')}",
                source_type=self.source_type,
                deadline=parse_date(item.get("close_date", "")),
                posted_date=parse_date(item.get("post_date", "")),
                funding_amount=item.get("estimated_total_program_funding"),
            )
            opportunities.append(opp)

        # Fetch next pages if available
        pagination = data.get("pagination", {})
        total_pages = pagination.get("total_pages", 1)
        if page < total_pages and page < 4:  # Max 4 pages
            more = await self._search(query, window_start, window_end, page + 1)
            opportunities.extend(more)

        return opportunities

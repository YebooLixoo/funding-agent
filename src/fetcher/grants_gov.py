"""Grants.gov Simpler API fetcher."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.fetcher import register_fetcher
from src.fetcher.base import BaseFetcher
from src.models import Opportunity
from src.utils import format_date_iso, parse_date

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.simpler.grants.gov/v1/opportunities/search"


@register_fetcher("grants_gov")
class GrantsGovFetcher(BaseFetcher):
    """Fetch from Grants.gov Simpler API.

    Rate limit: 60 requests/minute.
    Uses POST with JSON body for search.

    Note: The API nests post_date and close_date inside the `summary` object.
    Pagination metadata may be empty, so we fetch up to 4 pages and filter
    dates client-side.
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
            "artificial intelligence",
            "machine learning",
            "transportation",
            "autonomous vehicles",
        ]
        results: list[Opportunity] = []
        seen_ids: set[str] = set()

        window_start_str = format_date_iso(window_start)
        window_end_str = format_date_iso(window_end)

        for kw in keywords:
            try:
                opps = await self._search(kw, window_start_str, window_end_str)
                for opp in opps:
                    if opp.source_id not in seen_ids:
                        seen_ids.add(opp.source_id)
                        results.append(opp)
            except Exception:
                logger.exception(f"Grants.gov search failed for: {kw}")

        logger.info(f"Grants.gov: fetched {len(results)} opportunities")
        return results

    async def _search(
        self, query: str, window_start: str, window_end: str, page: int = 1
    ) -> list[Opportunity]:
        headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

        body = {
            "query": query,
            "filters": {
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

        now = datetime.now(timezone.utc)
        opportunities = []
        found_old = False

        for item in data.get("data", []):
            summary = item.get("summary", {}) if isinstance(item.get("summary"), dict) else {}

            # Extract dates from summary (API nests them there)
            post_date = parse_date(summary.get("post_date") or "")
            close_date = parse_date(summary.get("close_date") or "")

            # Client-side date window filter on post_date
            if post_date:
                post_str = post_date.strftime("%Y-%m-%d")
                if post_str < window_start:
                    found_old = True
                    continue
                if post_str > window_end:
                    continue

            # Determine opportunity status from API status field
            api_status = item.get("opportunity_status", "").lower()
            if api_status == "forecasted":
                opp_status = "coming_soon"
            else:
                opp_status = "open"

            # For open opportunities, skip past deadlines
            # For forecasted/coming_soon, deadline may be TBD — allow through
            if opp_status == "open" and close_date and close_date < now:
                logger.debug(
                    f"Grants.gov: skipping past deadline: {item.get('opportunity_title', '')[:60]}"
                )
                continue

            # Extract funding amount from summary
            funding = summary.get("estimated_total_program_funding")
            if funding:
                funding = f"${funding:,.0f}" if isinstance(funding, (int, float)) else str(funding)

            # Clean HTML from description
            desc_raw = summary.get("summary_description", "")
            if desc_raw:
                desc = re.sub(r"<[^>]+>", " ", desc_raw)
                desc = re.sub(r"\s+", " ", desc).strip()
            else:
                desc = ""

            opp = Opportunity(
                source=self.source_name,
                source_id=str(item.get("opportunity_id", "")),
                title=item.get("opportunity_title", ""),
                description=desc[:2000],
                url=f"https://simpler.grants.gov/opportunity/{item.get('opportunity_id', '')}",
                source_type=self.source_type,
                deadline=close_date,
                posted_date=post_date,
                funding_amount=funding,
                opportunity_status=opp_status,
            )
            opportunities.append(opp)

        # Fetch next pages if we haven't hit old results and got a full page
        items_count = len(data.get("data", []))
        if items_count >= 25 and not found_old and page < 4:
            more = await self._search(query, window_start, window_end, page + 1)
            opportunities.extend(more)

        return opportunities

    async def fetch_approaching_deadlines(
        self,
        keywords: list[str],
        lookahead_days: int = 30,
    ) -> list[Opportunity]:
        """Fetch opportunities with deadlines approaching within lookahead_days.

        Unlike the normal fetch (which filters by post_date), this searches
        by close_date to discover opportunities posted earlier but with
        deadlines approaching soon.

        Args:
            keywords: Search keywords.
            lookahead_days: Number of days ahead to look for deadlines.

        Returns:
            List of opportunities with approaching deadlines.
        """
        if not self.api_key:
            logger.warning("GRANTS_GOV_API_KEY not set, skipping deadline fetch")
            return []

        now = datetime.now(timezone.utc)
        deadline_limit = now + timedelta(days=lookahead_days)
        results: list[Opportunity] = []
        seen_ids: set[str] = set()

        for kw in keywords:
            try:
                opps = await self._search_by_deadline(kw, now, deadline_limit)
                for opp in opps:
                    if opp.source_id not in seen_ids:
                        seen_ids.add(opp.source_id)
                        results.append(opp)
            except Exception:
                logger.exception(f"Grants.gov deadline search failed for: {kw}")

        logger.info(f"Grants.gov: {len(results)} approaching-deadline opportunities")
        return results

    async def _search_by_deadline(
        self,
        query: str,
        now: datetime,
        deadline_limit: datetime,
        page: int = 1,
    ) -> list[Opportunity]:
        """Search sorted by close_date, filtering for approaching deadlines."""
        headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

        body = {
            "query": query,
            "filters": {
                "opportunity_status": {
                    "one_of": ["posted"],
                },
            },
            "pagination": {
                "page_offset": page,
                "page_size": 25,
                "sort_order": [
                    {
                        "order_by": "close_date",
                        "sort_direction": "ascending",
                    }
                ],
            },
        }

        resp = await self._post(_BASE_URL, json=body, headers=headers)
        data = resp.json()

        opportunities = []
        found_far = False

        for item in data.get("data", []):
            summary = item.get("summary", {}) if isinstance(item.get("summary"), dict) else {}

            post_date = parse_date(summary.get("post_date") or "")
            close_date = parse_date(summary.get("close_date") or "")

            # Skip items without a close_date
            if not close_date:
                continue

            # Skip past deadlines
            if close_date < now:
                continue

            # Stop if deadline is beyond our lookahead window
            if close_date > deadline_limit:
                found_far = True
                break

            funding = summary.get("estimated_total_program_funding")
            if funding:
                funding = f"${funding:,.0f}" if isinstance(funding, (int, float)) else str(funding)

            desc_raw = summary.get("summary_description", "")
            if desc_raw:
                desc = re.sub(r"<[^>]+>", " ", desc_raw)
                desc = re.sub(r"\s+", " ", desc).strip()
            else:
                desc = ""

            opp = Opportunity(
                source=self.source_name,
                source_id=str(item.get("opportunity_id", "")),
                title=item.get("opportunity_title", ""),
                description=desc[:2000],
                url=f"https://simpler.grants.gov/opportunity/{item.get('opportunity_id', '')}",
                source_type=self.source_type,
                deadline=close_date,
                posted_date=post_date,
                funding_amount=funding,
            )
            opportunities.append(opp)

        # Fetch next pages if we haven't gone past the deadline window
        items_count = len(data.get("data", []))
        if items_count >= 25 and not found_far and page < 4:
            more = await self._search_by_deadline(query, now, deadline_limit, page + 1)
            opportunities.extend(more)

        return opportunities

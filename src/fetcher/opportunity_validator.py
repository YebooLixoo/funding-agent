"""LLM-based opportunity validator using OpenAI GPT.

Shared validation gate for both industry web pages and government API results.
Identifies only real, active, currently-open funding opportunities.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from src.models import Opportunity
from src.utils import parse_date

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a strict funding opportunity validator for academic researchers.
Your job is to identify real funding opportunities (grants, awards, fellowships,
RFPs, calls for proposals) in two categories:

1. OPEN opportunities: Currently accepting applications.
2. COMING SOON opportunities: Announced/described but not yet open for applications.
   These include programs with ANY of these indicators:
   - "applications will open soon", "check back in [month]", "next cycle opens [date]"
   - Status marked as "TBD", "Forecasted", "Anticipated", "Expected", "Planned"
   - Close/deadline date shown as "TBD", "To Be Determined", or left blank with a future posting
   - "Pre-announcement", "Under development", "Forthcoming"
   - A recurring program that ran previously and is expected to reopen
   - Any language suggesting the opportunity will accept applications in the future

You MUST reject:
- Past/closed opportunities (deadline already passed, no future cycle mentioned)
- General company/lab pages that describe research areas but have no active or upcoming call
- Already-funded awards or completed projects
- Job postings, internships, or hiring pages
- News articles, blog posts, product announcements
- Generic program descriptions with no specific open or upcoming call

For OPEN opportunities, at least one of:
- An explicit application deadline in the future
- An explicit "applications now open" or "currently accepting" statement
- A "rolling deadline" or "open until filled" statement

For COMING SOON opportunities, at least one of:
- An anticipated opening date or application cycle mentioned
- Language indicating the program will accept applications in the future
- Status shown as TBD, Forecasted, Anticipated, Expected, or similar
- A deadline date shown as TBD or To Be Determined
- A recurring program that ran previously and is expected to reopen"""

_PAGE_VALIDATE_TEMPLATE = """Analyze this web page content from "{label}" ({url}).

FIRST: Is this page about funding opportunities, grants, or awards?
If it is a general research homepage, news page, or unrelated content, return [].

Extract opportunities in two categories:
1. OPEN: Currently accepting applications.
2. COMING SOON: Announced or described but not yet open. This includes opportunities with
   status "TBD", "Forecasted", "Anticipated", "Expected", or similar language, as well as
   deadlines shown as "TBD" or "To Be Determined". These are valuable for early awareness.

IMPORTANT: If the page lists multiple topics/tracks under a SHARED deadline or call
(e.g., "Spring 2026: Open Now — submission closes May 6"), each topic is a separate
opportunity that INHERITS the shared deadline. Apply the page-level deadline to each one.

For each opportunity found, extract:
- title: The specific opportunity/program name
- description: 1-2 sentence summary of what is funded
- deadline: Application deadline (ISO YYYY-MM-DD). Use null for coming_soon or rolling.
  If a page-level deadline applies to this opportunity, use that date.
- deadline_status: One of "explicit_date", "rolling", "shared" (inherited from page), "not_found"
- funding_amount: Dollar amount if mentioned, or null
- opportunity_status: "open" or "coming_soon"
- confidence: 0.0-1.0 how confident this is a real opportunity
  - 0.9+: Explicit deadline + clear application instructions
  - 0.7-0.8: Rolling/open deadline or shared deadline with clear "open now" language
  - 0.5-0.6: Coming soon with clear future dates/language, or TBD/Forecasted status
  - Below 0.5: General description, unlikely to be a real call

Today's date: {today}

Page content (truncated):
{content}

Respond with ONLY a JSON array. If no opportunities found, return [].
Example: [{{"title": "...", "description": "...", "deadline": "2026-06-15", "deadline_status": "explicit_date", "funding_amount": "$50K", "opportunity_status": "open", "confidence": 0.9}}]"""

_CLASSIFY_TEMPLATE = """Analyze this web page from "{label}" ({url}).

STEP 1: Classify this page:
- "opportunity_page": A specific funding opportunity with details (deadline, eligibility, application info)
- "landing_page": A general page that LISTS or LINKS TO multiple funding opportunities or programs
- "irrelevant": Not related to funding (news, about us, general info, blog)

STEP 2: If "opportunity_page", extract opportunity details with these fields:
- title, description, deadline (ISO YYYY-MM-DD or null), deadline_status ("explicit_date"|"rolling"|"shared"|"not_found"), funding_amount (or null), opportunity_status ("open"|"coming_soon"), confidence (0.0-1.0)
Note: Use "coming_soon" for opportunities that are announced but not yet accepting applications,
including those with status "TBD", "Forecasted", "Anticipated", or deadlines shown as "TBD".
If multiple topics share a page-level deadline, use deadline_status "shared" and apply the deadline to each.

STEP 3: If "landing_page", identify which links on this page likely point to specific funding opportunities or grant programs.
Here are the links found on this page:
{links_json}

Today's date: {today}

Page content (truncated):
{content}

Respond with ONLY a JSON object:
{{
  "page_type": "opportunity_page" | "landing_page" | "irrelevant",
  "opportunities": [...],
  "funding_links": [{{"url": "...", "label": "..."}}]
}}

If opportunity_page: fill "opportunities" array, leave "funding_links" empty.
If landing_page: fill "funding_links" with URLs pointing to grant/funding pages, "opportunities" can be empty.
If irrelevant: both arrays empty."""

_ITEM_SYSTEM_PROMPT = """You are a strict funding opportunity validator for academic researchers.
Your job is to identify real, currently-open funding opportunities (grants, awards, fellowships,
RFPs, calls for proposals) that are CURRENTLY ACCEPTING APPLICATIONS.

You MUST reject:
- Past/closed opportunities (deadline already passed)
- Forecasted or coming-soon opportunities that are not yet open
- General company/lab pages that describe research areas but have no active call
- Already-funded awards or completed projects
- Job postings, internships, or hiring pages
- News articles, blog posts, product announcements"""

_ITEM_VALIDATE_TEMPLATE = """Is this a real, currently-open funding opportunity
(grant, award, RFP, call for proposals) that is CURRENTLY ACCEPTING APPLICATIONS?

Title: {title}
Description: {description}
Deadline: {deadline}
URL: {url}

Today's date: {today}

Respond with ONLY a JSON object:
{{"is_valid": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}"""

# Confidence threshold for accepting opportunities
_PAGE_CONFIDENCE_THRESHOLD = 0.6


class OpportunityValidator:
    """LLM-powered validator for funding opportunities.

    Used by both industry web scraper and government API fetchers
    to ensure only real, active opportunities are returned.
    """

    def __init__(self, model: str = "gpt-5.2") -> None:
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI()
            except Exception:
                logger.warning("OpenAI client not available, validator disabled")
        return self._client

    def validate_page_content(
        self,
        text: str,
        url: str,
        label: str,
        source_name: str,
        source_type: str = "industry",
    ) -> list[Opportunity]:
        """Validate page content and extract real, open opportunities.

        Args:
            text: Cleaned page text content.
            url: Source URL.
            label: Human-readable source label.
            source_name: Source identifier for Opportunity.source field.
            source_type: 'industry' or 'government'.

        Returns:
            List of validated Opportunity objects. Empty if no real ones found.
        """
        client = self._get_client()
        if client is None:
            logger.warning(f"Validator unavailable, skipping {label}")
            return []

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        prompt = _PAGE_VALIDATE_TEMPLATE.format(
            label=label,
            url=url,
            today=today,
            content=text[:6000],
        )

        try:
            response = client.chat.completions.create(
                model=self.model,
                max_completion_tokens=1000,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = response.choices[0].message.content.strip()
            return self._parse_page_response(raw, url, source_name, source_type)
        except Exception:
            logger.exception(f"Page validation failed for {label}")
            return []

    def classify_and_extract(
        self,
        text: str,
        url: str,
        label: str,
        links: list[dict],
        source_name: str,
        source_type: str = "industry",
    ) -> tuple[str, list[Opportunity], list[tuple[str, str]]]:
        """Classify a page and extract opportunities or funding links.

        Args:
            text: Cleaned page text content.
            url: Source URL.
            label: Human-readable source label.
            links: List of {"url": ..., "text": ...} dicts from the page.
            source_name: Source identifier for Opportunity.source field.
            source_type: 'industry' or 'government'.

        Returns:
            Tuple of (page_type, opportunities, funding_links).
            page_type: 'opportunity_page', 'landing_page', or 'irrelevant'.
            opportunities: Extracted Opportunity objects (if opportunity_page).
            funding_links: List of (url, label) tuples to follow (if landing_page).
        """
        client = self._get_client()
        if client is None:
            logger.warning(f"Validator unavailable, skipping {label}")
            return "irrelevant", [], []

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Limit links to keep prompt manageable
        links_truncated = links[:50]
        links_json = json.dumps(links_truncated, indent=2)[:3000]

        prompt = _CLASSIFY_TEMPLATE.format(
            label=label,
            url=url,
            today=today,
            content=text[:5000],
            links_json=links_json,
        )

        try:
            response = client.chat.completions.create(
                model=self.model,
                max_completion_tokens=1500,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = response.choices[0].message.content.strip()
            return self._parse_classify_response(raw, url, source_name, source_type)
        except Exception:
            logger.exception(f"Page classification failed for {label}")
            return "irrelevant", [], []

    def _parse_classify_response(
        self, raw: str, url: str, source_name: str, source_type: str
    ) -> tuple[str, list[Opportunity], list[tuple[str, str]]]:
        """Parse LLM classification response."""
        # Strip markdown code fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]
        raw = raw.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse classify response: {raw[:200]}")
            return "irrelevant", [], []

        page_type = data.get("page_type", "irrelevant")

        # Parse opportunities
        opportunities = []
        if page_type == "opportunity_page":
            opportunities = self._parse_page_response(
                json.dumps(data.get("opportunities", [])),
                url, source_name, source_type,
            )

        # Parse funding links
        funding_links: list[tuple[str, str]] = []
        if page_type == "landing_page":
            for link in data.get("funding_links", []):
                link_url = link.get("url", "")
                link_label = link.get("label", "")
                if link_url and link_url.startswith("http"):
                    funding_links.append((link_url, link_label))

        return page_type, opportunities, funding_links

    def validate_opportunity(
        self,
        title: str,
        description: str,
        deadline: Optional[str],
        url: str,
    ) -> tuple[bool, float, str]:
        """Validate a single government opportunity.

        Args:
            title: Opportunity title.
            description: Opportunity description.
            deadline: Deadline string or None.
            url: Opportunity URL.

        Returns:
            Tuple of (is_valid, confidence, reason).
        """
        client = self._get_client()
        if client is None:
            return True, 0.5, "Validator unavailable, accepting by default"

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        prompt = _ITEM_VALIDATE_TEMPLATE.format(
            title=title,
            description=description[:2000],
            deadline=deadline or "Not specified",
            url=url,
            today=today,
        )

        try:
            response = client.chat.completions.create(
                model=self.model,
                max_completion_tokens=200,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": _ITEM_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = response.choices[0].message.content.strip()
            return self._parse_item_response(raw)
        except Exception:
            logger.exception(f"Item validation failed for: {title[:60]}")
            return True, 0.5, "Validation error, accepting by default"

    def _parse_page_response(
        self, raw: str, url: str, source_name: str, source_type: str = "industry"
    ) -> list[Opportunity]:
        """Parse LLM page validation response into Opportunity objects."""
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]
        raw = raw.strip()

        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response as JSON: {raw[:200]}")
            return []

        if not isinstance(items, list):
            return []

        opportunities = []
        now = datetime.now(timezone.utc)

        for item in items:
            confidence = float(item.get("confidence", 0.0))
            if confidence < _PAGE_CONFIDENCE_THRESHOLD:
                logger.debug(
                    f"Rejected (confidence={confidence:.2f}): {item.get('title', '')[:60]}"
                )
                continue

            opp_status = item.get("opportunity_status", "open")
            deadline = parse_date(item.get("deadline") or "")

            if opp_status == "open":
                # Open opportunities: enforce deadline checks
                if deadline and deadline < now:
                    logger.debug(
                        f"Rejected (past deadline): {item.get('title', '')[:60]}"
                    )
                    continue

                deadline_status = item.get("deadline_status", "not_found")
                if not deadline and deadline_status not in ("rolling",):
                    logger.debug(
                        f"Rejected (no deadline, status={deadline_status}): "
                        f"{item.get('title', '')[:60]}"
                    )
                    continue
            # coming_soon: no deadline required, skip deadline checks

            title = item.get("title", "")
            item_hash = hashlib.md5(title.encode()).hexdigest()[:8]

            opp = Opportunity(
                source=source_name,
                source_id=f"{source_name}_{item_hash}",
                title=title,
                description=item.get("description", ""),
                url=url,
                source_type=source_type,
                deadline=deadline,
                funding_amount=item.get("funding_amount"),
                posted_date=now,
                opportunity_status=opp_status if opp_status in ("open", "coming_soon") else "open",
            )
            opportunities.append(opp)

        return opportunities

    def _parse_item_response(self, raw: str) -> tuple[bool, float, str]:
        """Parse LLM item validation response."""
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]
        raw = raw.strip()

        try:
            data = json.loads(raw)
            is_valid = bool(data.get("is_valid", False))
            confidence = float(data.get("confidence", 0.5))
            reason = str(data.get("reason", ""))
            return is_valid, confidence, reason
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"Failed to parse item validation: {raw[:200]}")
            return True, 0.5, "Parse error, accepting by default"

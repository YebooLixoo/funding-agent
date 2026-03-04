"""LLM-based opportunity validator using OpenAI GPT.

Shared validation gate for both industry web pages and government API results.
Identifies only real, active, currently-open funding opportunities.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from src.models import Opportunity
from src.utils import parse_date

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a funding opportunity validator for academic researchers.
Your job is to identify ONLY real, active, currently-open funding opportunities
(grants, awards, fellowships, RFPs, calls for proposals).

Reject:
- Past/closed opportunities (deadline already passed)
- General company pages, news articles, product announcements
- Already-funded awards or completed projects
- Job postings, internships, or hiring pages
- Generic research lab descriptions with no active call"""

_PAGE_VALIDATE_TEMPLATE = """Analyze this web page content from "{label}" ({url}).

Extract ALL real, currently-open funding opportunities. For each one, provide:
- title: The opportunity name
- description: 1-2 sentence summary
- deadline: Application deadline (ISO format YYYY-MM-DD, or null if unknown)
- funding_amount: Dollar amount if mentioned, or null
- confidence: 0.0-1.0 how confident this is a real, open opportunity

Today's date: {today}

Page content (truncated):
{content}

Respond with ONLY a JSON array. If no real opportunities found, return [].
Example: [{{"title": "...", "description": "...", "deadline": "2026-06-15", "funding_amount": "$50K", "confidence": 0.8}}]"""

_ITEM_VALIDATE_TEMPLATE = """Is this a real, currently-open funding opportunity (grant, award, RFP, call for proposals)?

Title: {title}
Description: {description}
Deadline: {deadline}
URL: {url}

Today's date: {today}

Respond with ONLY a JSON object:
{{"is_valid": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}"""


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
    ) -> list[Opportunity]:
        """Validate industry page content and extract real opportunities.

        Args:
            text: Cleaned page text content.
            url: Source URL.
            label: Human-readable source label.
            source_name: Source identifier for Opportunity.source field.

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
            return self._parse_page_response(raw, url, source_name)
        except Exception:
            logger.exception(f"Page validation failed for {label}")
            return []

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
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = response.choices[0].message.content.strip()
            return self._parse_item_response(raw)
        except Exception:
            logger.exception(f"Item validation failed for: {title[:60]}")
            return True, 0.5, "Validation error, accepting by default"

    def _parse_page_response(
        self, raw: str, url: str, source_name: str
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
            if confidence < 0.5:
                continue

            deadline = parse_date(item.get("deadline") or "")
            if deadline and deadline < now:
                continue

            import hashlib
            title = item.get("title", "")
            item_hash = hashlib.md5(title.encode()).hexdigest()[:8]

            opp = Opportunity(
                source=source_name,
                source_id=f"{source_name}_{item_hash}",
                title=f"{title}",
                description=item.get("description", ""),
                url=url,
                source_type="industry",
                deadline=deadline,
                funding_amount=item.get("funding_amount"),
                posted_date=now,
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

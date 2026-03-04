"""LLM-powered opportunity summarization."""

from __future__ import annotations

import logging
import os
from typing import Optional

from src.models import Opportunity
from src.utils import format_date

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a research funding assistant. Generate concise summaries of funding opportunities
for a Computer Science professor focused on AI/ML applied to transportation and infrastructure."""

_USER_TEMPLATE = """Summarize this funding opportunity in 2-3 sentences, highlighting:
1. What the funding supports
2. Relevance to AI + transportation research
3. Key requirements or eligibility

Title: {title}
Description: {description}
Deadline: {deadline}
Amount: {amount}

Respond with ONLY the summary, no preamble."""


class Summarizer:
    """Generate concise summaries of funding opportunities using Claude Haiku."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001") -> None:
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic()
            except Exception:
                logger.warning("Anthropic client not available, using template summaries")
        return self._client

    async def summarize(self, opp: Opportunity) -> str:
        """Generate a summary for an opportunity.

        Falls back to template-based summary if LLM is unavailable.
        """
        client = self._get_client()
        if client is None:
            return self._template_summary(opp)

        try:
            message = client.messages.create(
                model=self.model,
                max_tokens=200,
                temperature=0.2,
                system=_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": _USER_TEMPLATE.format(
                            title=opp.title,
                            description=opp.description[:1500],
                            deadline=format_date(opp.deadline),
                            amount=opp.funding_amount or "Not specified",
                        ),
                    }
                ],
            )
            return message.content[0].text.strip()

        except Exception:
            logger.exception(f"Summarization failed for: {opp.title[:60]}")
            return self._template_summary(opp)

    async def summarize_batch(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        """Summarize a batch of opportunities.

        Returns new Opportunity instances with summaries filled in.
        """
        results = []
        for opp in opportunities:
            summary = await self.summarize(opp)
            new_opp = Opportunity(
                source=opp.source,
                source_id=opp.source_id,
                title=opp.title,
                description=opp.description,
                url=opp.url,
                source_type=opp.source_type,
                deadline=opp.deadline,
                posted_date=opp.posted_date,
                funding_amount=opp.funding_amount,
                keywords=opp.keywords,
                relevance_score=opp.relevance_score,
                summary=summary,
            )
            results.append(new_opp)

        logger.info(f"Summarized {len(results)} opportunities")
        return results

    def _template_summary(self, opp: Opportunity) -> str:
        """Fallback template-based summary."""
        parts = [opp.title]
        if opp.funding_amount:
            parts.append(f"Funding: {opp.funding_amount}.")
        if opp.deadline:
            parts.append(f"Deadline: {format_date(opp.deadline)}.")
        desc_snippet = opp.description[:200].strip()
        if desc_snippet:
            parts.append(desc_snippet + ("..." if len(opp.description) > 200 else ""))
        return " ".join(parts)

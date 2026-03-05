"""LLM-powered opportunity summarization using OpenAI GPT."""

from __future__ import annotations

import logging
import os
from typing import Optional

from src.models import Opportunity
from src.utils import format_date

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a research funding assistant. Generate concise summaries of funding opportunities
for an assistant professor in Civil & Environmental Engineering (transportation engineering focus) with a CS PhD.
The professor's interests span autonomous vehicles, V2X, smart infrastructure, network science/resilience,
civil engineering empowered by AI, general AI/ML, data science, and operations research.
As a young faculty member, early career awards are also highly relevant."""

_USER_TEMPLATE = """Summarize this funding opportunity in 2-3 sentences, highlighting:
1. What the funding supports
2. Relevance to the professor's research (AI, transportation, civil engineering, data science, or early career)
3. Key requirements or eligibility

Title: {title}
Description: {description}
Deadline: {deadline}
Amount: {amount}

Respond with ONLY the summary, no preamble."""


class Summarizer:
    """Generate concise summaries of funding opportunities using OpenAI GPT."""

    def __init__(self, model: str = "gpt-5.2") -> None:
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI()
            except Exception:
                logger.warning("OpenAI client not available, using template summaries")
        return self._client

    async def summarize(self, opp: Opportunity) -> str:
        """Generate a summary for an opportunity.

        Falls back to template-based summary if LLM is unavailable.
        """
        client = self._get_client()
        if client is None:
            return self._template_summary(opp)

        try:
            response = client.chat.completions.create(
                model=self.model,
                max_completion_tokens=200,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": _USER_TEMPLATE.format(
                            title=opp.title,
                            description=opp.description[:1500],
                            deadline=format_date(opp.deadline),
                            amount=opp.funding_amount or "Not specified",
                        ),
                    },
                ],
            )
            return response.choices[0].message.content.strip()

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

"""Claude Haiku LLM-based relevance filter for borderline cases."""

from __future__ import annotations

import logging
import os
from typing import Optional

from src.models import Opportunity

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a research funding relevance evaluator for a Computer Science professor.
The professor focuses on:
- AI/ML applied to transportation, autonomous vehicles, smart infrastructure
- Deep learning, computer vision, NLP for transportation systems
- Energy grid optimization, disaster resilience, smart cities

Evaluate whether the following funding opportunity is relevant to this professor's research."""

_USER_TEMPLATE = """Title: {title}
Description: {description}

Rate this opportunity's relevance from 0.0 to 1.0 and provide a brief justification.
Respond in this exact format:
SCORE: <float>
REASON: <one sentence>"""


class LLMFilter:
    """Use Claude Haiku to evaluate borderline opportunities.

    Only invoked for opportunities with keyword scores between 0.3-0.6.
    Cost: ~$0.01 per call.
    """

    def __init__(self, model: str = "claude-haiku-4-5-20251001") -> None:
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic()
            except Exception:
                logger.warning("Anthropic client not available, LLM filter disabled")
        return self._client

    async def evaluate(self, opp: Opportunity) -> tuple[float, str]:
        """Evaluate a single opportunity with Claude Haiku.

        Returns:
            Tuple of (score, reason).
        """
        client = self._get_client()
        if client is None:
            return opp.relevance_score, "LLM unavailable, using keyword score"

        try:
            message = client.messages.create(
                model=self.model,
                max_tokens=150,
                temperature=0.1,
                system=_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": _USER_TEMPLATE.format(
                            title=opp.title,
                            description=opp.description[:1500],
                        ),
                    }
                ],
            )

            response_text = message.content[0].text
            return self._parse_response(response_text)

        except Exception:
            logger.exception(f"LLM evaluation failed for: {opp.title[:60]}")
            return opp.relevance_score, "LLM evaluation failed"

    def _parse_response(self, text: str) -> tuple[float, str]:
        """Parse LLM response into score and reason."""
        score = 0.5
        reason = ""

        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("SCORE:"):
                try:
                    score = float(line.split(":", 1)[1].strip())
                    score = max(0.0, min(1.0, score))
                except ValueError:
                    pass
            elif line.startswith("REASON:"):
                reason = line.split(":", 1)[1].strip()

        return score, reason

    async def filter_borderline(
        self, opportunities: list[Opportunity], threshold: float = 0.5
    ) -> list[Opportunity]:
        """Evaluate and filter borderline opportunities.

        Args:
            opportunities: Borderline opportunities from keyword filter.
            threshold: LLM score threshold for acceptance.

        Returns:
            Opportunities that passed LLM review.
        """
        accepted = []
        for opp in opportunities:
            score, reason = await self.evaluate(opp)
            logger.debug(f"LLM score={score:.2f} for: {opp.title[:60]} ({reason})")

            if score >= threshold:
                accepted_opp = Opportunity(
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
                    relevance_score=score,
                    summary=reason,
                )
                accepted.append(accepted_opp)

        logger.info(
            f"LLM filter: {len(accepted)}/{len(opportunities)} borderline accepted"
        )
        return accepted

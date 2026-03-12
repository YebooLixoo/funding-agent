"""OpenAI GPT-based relevance filter for borderline cases."""

from __future__ import annotations

import logging
import os
from typing import Optional

from src.models import Opportunity

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a research funding relevance evaluator for an assistant professor.

Profile:
- Position: Assistant professor in Civil & Environmental Engineering (transportation engineering focus), with a CS PhD
- Core research: Autonomous vehicles, V2X (vehicle-to-everything), smart infrastructure, connected vehicles, transportation networks, network resilience, network science
- Broad interests: Any civil engineering area empowered by AI, general AI/ML, data science, operations research, routing, statistics
- Career stage: Young faculty — eligible for early career awards (NSF CAREER, DOE Early Career, DARPA YFA, ONR YIP, etc.)

RELEVANT — score 0.5 or higher:
1. AI/ML applied to transportation, civil engineering, or infrastructure
2. Pure AI/ML or data science research grants
3. Civil engineering, structural engineering, environmental engineering, water resources, hazards/resilience
4. Network science, optimization, operations research
5. Early career awards or young investigator programs for engineering/CS faculty
6. Smart cities, connected vehicles, autonomous systems

NOT RELEVANT — score below 0.3 (MUST exclude):
- Pure biology, neuroscience, or biomedical research (e.g., BRAIN Initiative, cell atlas, neural circuits)
- Clinical trials, drug discovery, pharmaceutical research
- Genomics, proteomics, molecular biology, biochemistry, immunology, oncology, pathology
- Social sciences, humanities, arts, education research
- Medical device development or clinical medicine
- Psychology or cognitive science without engineering application"""

_USER_TEMPLATE = """Title: {title}
Description: {description}

Rate this opportunity's relevance from 0.0 to 1.0 and provide a brief justification.
Respond in this exact format:
SCORE: <float>
REASON: <one sentence>"""


class LLMFilter:
    """Use OpenAI GPT to evaluate borderline opportunities.

    Only invoked for opportunities with keyword scores between 0.3-0.6.
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
                logger.warning("OpenAI client not available, LLM filter disabled")
        return self._client

    async def evaluate(self, opp: Opportunity) -> tuple[float, str]:
        """Evaluate a single opportunity with GPT.

        Returns:
            Tuple of (score, reason).
        """
        client = self._get_client()
        if client is None:
            return opp.relevance_score, "LLM unavailable, using keyword score"

        try:
            response = client.chat.completions.create(
                model=self.model,
                max_completion_tokens=150,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": _USER_TEMPLATE.format(
                            title=opp.title,
                            description=opp.description[:1500],
                        ),
                    },
                ],
            )

            response_text = response.choices[0].message.content
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

"""Fast keyword-based relevance filtering."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from src.models import Opportunity

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FilterConfig:
    """Filter configuration."""

    primary_keywords: list[str]
    domain_keywords: list[str]
    exclusions: list[str]
    keyword_threshold: float = 0.3


class KeywordFilter:
    """Fast first-pass keyword relevance filter.

    Scoring:
    - Primary keyword match (AI-related): 0.4 per match (max 0.6)
    - Domain keyword match (transportation): 0.2 per match (max 0.4)
    - Exclusion match: set score to 0.0
    """

    def __init__(self, config: FilterConfig) -> None:
        self.config = config
        self._primary_patterns = [
            re.compile(re.escape(kw), re.IGNORECASE) for kw in config.primary_keywords
        ]
        self._domain_patterns = [
            re.compile(re.escape(kw), re.IGNORECASE) for kw in config.domain_keywords
        ]
        self._exclusion_patterns = [
            re.compile(re.escape(ex), re.IGNORECASE) for ex in config.exclusions
        ]

    def score(self, opp: Opportunity) -> float:
        """Compute relevance score for an opportunity.

        Returns:
            Float between 0.0 and 1.0.
        """
        text = f"{opp.title} {opp.description}"

        # Check exclusions first
        for pat in self._exclusion_patterns:
            if pat.search(text):
                logger.debug(f"Excluded: {opp.title[:60]}")
                return 0.0

        # Primary AI keywords
        primary_count = sum(1 for pat in self._primary_patterns if pat.search(text))
        primary_score = min(primary_count * 0.4, 0.6)

        # Domain keywords
        domain_count = sum(1 for pat in self._domain_patterns if pat.search(text))
        domain_score = min(domain_count * 0.2, 0.4)

        total = primary_score + domain_score
        return min(total, 1.0)

    def filter(self, opportunities: list[Opportunity]) -> tuple[list[Opportunity], list[Opportunity]]:
        """Filter opportunities into accepted and borderline.

        Returns:
            Tuple of (accepted, borderline) lists.
            - Accepted: score >= threshold
            - Borderline: score between llm_review_min and llm_review_max
        """
        accepted = []
        borderline = []

        for opp in opportunities:
            s = self.score(opp)
            scored_opp = Opportunity(
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
                relevance_score=s,
                summary=opp.summary,
            )

            if s >= 0.6:
                accepted.append(scored_opp)
            elif s >= self.config.keyword_threshold:
                borderline.append(scored_opp)
            else:
                logger.debug(f"Rejected (score={s:.2f}): {opp.title[:60]}")

        logger.info(
            f"Keyword filter: {len(accepted)} accepted, {len(borderline)} borderline, "
            f"{len(opportunities) - len(accepted) - len(borderline)} rejected"
        )
        return accepted, borderline

    def extract_matching_keywords(self, opp: Opportunity) -> list[str]:
        """Extract keywords that matched for an opportunity."""
        text = f"{opp.title} {opp.description}"
        matched = []
        for kw, pat in zip(self.config.primary_keywords, self._primary_patterns):
            if pat.search(text):
                matched.append(kw)
        for kw, pat in zip(self.config.domain_keywords, self._domain_patterns):
            if pat.search(text):
                matched.append(kw)
        return matched

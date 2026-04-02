"""Fast keyword-based relevance filtering with multi-track scoring."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from src.models import Opportunity

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FilterConfig:
    """Filter configuration."""

    primary_keywords: list[str]
    domain_keywords: list[str]
    exclusions: list[str]
    career_keywords: list[str] = field(default_factory=list)
    faculty_keywords: list[str] = field(default_factory=list)
    compute_keywords: list[str] = field(default_factory=list)
    keyword_threshold: float = 0.3


class KeywordFilter:
    """Fast first-pass keyword relevance filter with multi-track scoring.

    Two independent scoring tracks:
    - Track 1 (AI+Domain): primary 0.4/match (max 0.6) + domain 0.2/match (max 0.4)
    - Track 2 (Career+Faculty): career 0.35/match (max 0.5) + faculty 0.15/match (max 0.2)
    - Cross-bonus: career+domain → +0.15, career+primary → +0.2
    - Final: max(track1, track2) + cross_bonus, capped at 1.0
    """

    _HEALTH_ADJACENT = re.compile(
        r'(?:health|medical|clinical|patient|hospital|treatment|disease|'
        r'disorder|wellness|healthcare|care delivery|health care|'
        r'health system|health intervention|health outcome|health disparity|'
        r'health equity|maternal|pediatric|geriatric|surgical|diagnostic|'
        r'therapeutic|rehabilitation|nursing|pharmacy|dentistry|veterinary)',
        re.IGNORECASE,
    )
    _ENGINEERING_CONTEXT = re.compile(
        r'(?:civil engineering|transportation|infrastructure|'
        r'environmental engineering|air quality|water quality|'
        r'smart city|sensor|IoT|monitoring system|'
        r'building|HVAC|ventilation|indoor environment|'
        r'construction|structural|geotechnical|'
        r'traffic|vehicle|mobility|highway|road|bridge|pavement|'
        r'stormwater|wastewater|water treatment|remediation|pollution|'
        r'wildfire|flood|earthquake|hurricane|hazard|emergency management|'
        r'urban planning|land use|resilient infrastructure)',
        re.IGNORECASE,
    )

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
        self._career_patterns = [
            re.compile(re.escape(kw), re.IGNORECASE) for kw in config.career_keywords
        ]
        self._faculty_patterns = [
            re.compile(re.escape(kw), re.IGNORECASE) for kw in config.faculty_keywords
        ]
        self._compute_patterns = [
            re.compile(re.escape(kw), re.IGNORECASE) for kw in config.compute_keywords
        ]

    def is_excluded(self, opp: Opportunity) -> bool:
        """Check if an opportunity matches any exclusion pattern."""
        text = f"{opp.title} {opp.description}"
        for pat in self._exclusion_patterns:
            if pat.search(text):
                return True
        if self._HEALTH_ADJACENT.search(text) and not self._ENGINEERING_CONTEXT.search(text):
            return True
        return False

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

        # Domain-context check: health-adjacent topics need engineering context
        if self._HEALTH_ADJACENT.search(text) and not self._ENGINEERING_CONTEXT.search(text):
            # Health-adjacent content without engineering context → reject
            logger.debug(f"Health-context rejected: {opp.title[:60]}")
            return 0.0

        # Track 1: AI + Domain
        primary_count = sum(1 for pat in self._primary_patterns if pat.search(text))
        primary_score = min(primary_count * 0.4, 0.6)

        domain_count = sum(1 for pat in self._domain_patterns if pat.search(text))
        domain_score = min(domain_count * 0.2, 0.4)

        track1 = primary_score + domain_score

        # Track 2: Career + Faculty
        career_count = sum(1 for pat in self._career_patterns if pat.search(text))
        career_score = min(career_count * 0.35, 0.5)

        faculty_count = sum(1 for pat in self._faculty_patterns if pat.search(text))
        faculty_score = min(faculty_count * 0.15, 0.2)

        track2 = career_score + faculty_score

        # Track 3: Compute resources
        compute_count = sum(1 for pat in self._compute_patterns if pat.search(text))
        compute_score = min(compute_count * 0.3, 0.5)

        # Curated compute sources get a floor score (pre-validated relevance)
        if hasattr(opp, 'source_type') and opp.source_type == 'compute':
            compute_score = max(compute_score, 0.4)

        # Cross-bonus: career keywords combined with domain or primary
        cross_bonus = 0.0
        if career_count > 0 and domain_count > 0:
            cross_bonus += 0.15
        if career_count > 0 and primary_count > 0:
            cross_bonus += 0.2
        # Compute + primary (AI compute resources)
        if compute_count > 0 and primary_count > 0:
            cross_bonus += 0.15

        total = max(track1, track2, compute_score) + cross_bonus
        return min(total, 1.0)

    def filter(self, opportunities: list[Opportunity]) -> tuple[list[Opportunity], list[Opportunity]]:
        """Filter opportunities into accepted and borderline.

        Returns:
            Tuple of (accepted, borderline) lists.
            - Accepted: score >= 0.6
            - Borderline: score between threshold and 0.6
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
                opportunity_status=opp.opportunity_status,
                deadline_type=opp.deadline_type,
                resource_type=opp.resource_type,
                resource_provider=opp.resource_provider,
                resource_scale=opp.resource_scale,
                allocation_details=opp.allocation_details,
                eligibility=opp.eligibility,
                access_url=opp.access_url,
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
        for kw, pat in zip(self.config.career_keywords, self._career_patterns):
            if pat.search(text):
                matched.append(kw)
        for kw, pat in zip(self.config.faculty_keywords, self._faculty_patterns):
            if pat.search(text):
                matched.append(kw)
        for kw, pat in zip(self.config.compute_keywords, self._compute_patterns):
            if pat.search(text):
                matched.append(kw)
        return matched

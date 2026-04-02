"""Per-user multi-signal recommendation scoring service.

Combines four signals to produce a final relevance score:
  - Keyword match (40%): Existing multi-track keyword filter, weighted by UserKeyword.weight
  - Profile match (30%): Text similarity between user profile and opportunity
  - Behavioral (20%): Boost from bookmarks, penalize from dismissals on similar opps
  - Urgency (10%): Deadline proximity and recency boost

Final score = 0.4*keyword + 0.3*profile + 0.2*behavior + 0.1*urgency, capped at 1.0
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.models.keyword import UserKeyword
from web.models.opportunity import Opportunity, UserOpportunityScore
from web.models.user import User

# Import the proven internal scoring algorithm and data model
from src.filter.keyword_filter import FilterConfig, KeywordFilter
from src.models import Opportunity as InternalOpportunity

logger = logging.getLogger(__name__)

# Signal weights
W_KEYWORD = 0.40
W_PROFILE = 0.30
W_BEHAVIOR = 0.20
W_URGENCY = 0.10


# ---------------------------------------------------------------------------
# Signal 1: Keyword Score (with per-keyword weights)
# ---------------------------------------------------------------------------

async def build_filter_config(db: AsyncSession, user_id) -> tuple[FilterConfig, dict[str, float]]:
    """Build a FilterConfig from a user's keywords, returning weights map too."""
    result = await db.execute(
        select(UserKeyword).where(
            UserKeyword.user_id == user_id,
            UserKeyword.is_active.is_(True),
        )
    )
    keywords = result.scalars().all()

    primary = []
    domain = []
    career = []
    faculty = []
    compute = []
    exclusions = []
    weights_map: dict[str, float] = {}

    for kw in keywords:
        weights_map[kw.keyword.lower()] = kw.weight or 1.0
        if kw.category == "primary":
            primary.append(kw.keyword)
        elif kw.category == "domain":
            domain.append(kw.keyword)
        elif kw.category == "career":
            career.append(kw.keyword)
        elif kw.category == "faculty":
            faculty.append(kw.keyword)
        elif kw.category == "exclusion":
            exclusions.append(kw.keyword)
        elif kw.category == "compute":
            compute.append(kw.keyword)
        elif kw.category == "custom":
            primary.append(kw.keyword)

    config = FilterConfig(
        primary_keywords=primary,
        domain_keywords=domain,
        career_keywords=career,
        faculty_keywords=faculty,
        compute_keywords=compute,
        exclusions=exclusions,
    )
    return config, weights_map


def _compute_keyword_score(
    kf: KeywordFilter, opp: InternalOpportunity, weights_map: dict[str, float]
) -> float:
    """Keyword score with per-keyword weight multipliers."""
    base_score = kf.score(opp)
    if not weights_map or base_score == 0.0:
        return base_score

    # Apply weight boost: average weight of matched keywords
    matched = kf.extract_matching_keywords(opp)
    if not matched:
        return base_score

    avg_weight = sum(weights_map.get(m.lower(), 1.0) for m in matched) / len(matched)
    return min(base_score * avg_weight, 1.0)


# ---------------------------------------------------------------------------
# Signal 2: Profile Match
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "has", "have", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "this", "that", "these",
    "those", "i", "we", "my", "our", "their", "its", "it", "not", "no",
    "as", "if", "so", "than", "very", "also", "such", "about", "into",
})


def _extract_terms(text: str) -> Counter:
    """Extract meaningful terms from text as a frequency counter."""
    words = re.findall(r'[a-z]{3,}', text.lower())
    return Counter(w for w in words if w not in _STOP_WORDS)


def _compute_profile_score(user: User, opp_text: str) -> float:
    """Score based on overlap between user profile and opportunity text."""
    # Build profile text from all available fields
    profile_parts = []
    if user.research_summary:
        profile_parts.append(user.research_summary)
    if user.department:
        profile_parts.append(user.department)
    if user.position:
        profile_parts.append(user.position)
    if user.institution:
        profile_parts.append(user.institution)

    if not profile_parts:
        return 0.0

    profile_text = " ".join(profile_parts)
    profile_terms = _extract_terms(profile_text)
    opp_terms = _extract_terms(opp_text)

    if not profile_terms or not opp_terms:
        return 0.0

    # Compute Jaccard-like overlap weighted by term frequency
    shared_terms = set(profile_terms.keys()) & set(opp_terms.keys())
    if not shared_terms:
        return 0.0

    # Weight by how important each shared term is in the profile
    weighted_overlap = sum(profile_terms[t] for t in shared_terms)
    total_profile_weight = sum(profile_terms.values())

    raw_score = weighted_overlap / total_profile_weight
    # Scale up: even 20% overlap is quite good
    return min(raw_score * 3.0, 1.0)


# ---------------------------------------------------------------------------
# Signal 3: Behavioral Score
# ---------------------------------------------------------------------------

async def _compute_behavior_score(
    db: AsyncSession, user_id, opp: Opportunity, opp_keywords: list[str]
) -> float:
    """Score based on similarity to bookmarked/dismissed opportunities."""
    # Get user's bookmarked and dismissed opportunity keywords
    bookmark_result = await db.execute(
        select(UserOpportunityScore).where(
            UserOpportunityScore.user_id == user_id,
            UserOpportunityScore.is_bookmarked.is_(True),
        )
    )
    bookmarked = bookmark_result.scalars().all()

    dismiss_result = await db.execute(
        select(UserOpportunityScore).where(
            UserOpportunityScore.user_id == user_id,
            UserOpportunityScore.is_dismissed.is_(True),
        )
    )
    dismissed = dismiss_result.scalars().all()

    if not bookmarked and not dismissed:
        return 0.5  # Neutral when no behavior data

    opp_kw_set = set(k.lower() for k in opp_keywords) if opp_keywords else set()
    if not opp_kw_set:
        return 0.5

    # Compute boost from bookmarked items
    boost = 0.0
    if bookmarked:
        for score_record in bookmarked:
            bm_keywords = score_record.matched_keywords or []
            bm_set = set(k.lower() for k in bm_keywords)
            if bm_set:
                overlap = len(opp_kw_set & bm_set) / max(len(opp_kw_set | bm_set), 1)
                boost += overlap
        boost = boost / len(bookmarked)  # Average overlap

    # Compute penalty from dismissed items
    penalty = 0.0
    if dismissed:
        for score_record in dismissed:
            dm_keywords = score_record.matched_keywords or []
            dm_set = set(k.lower() for k in dm_keywords)
            if dm_set:
                overlap = len(opp_kw_set & dm_set) / max(len(opp_kw_set | dm_set), 1)
                penalty += overlap
        penalty = penalty / len(dismissed)

    # Combine: base 0.5, boost up to +0.5, penalty down to -0.5
    return max(0.0, min(1.0, 0.5 + boost * 0.5 - penalty * 0.5))


# ---------------------------------------------------------------------------
# Signal 4: Urgency Score
# ---------------------------------------------------------------------------

def _compute_urgency_score(opp: Opportunity) -> float:
    """Score based on deadline proximity and recency."""
    now = datetime.now(timezone.utc)
    score = 0.0

    # Rolling/quarterly: base urgency + deadline proximity if next review date is set
    if getattr(opp, 'deadline_type', 'fixed') in ('rolling', 'quarterly'):
        score += 0.35
        # Quarterly with computed next review date: add proximity boost
        if getattr(opp, 'deadline_type', 'fixed') == 'quarterly' and opp.deadline:
            try:
                deadline_dt = datetime.fromisoformat(opp.deadline)
                if deadline_dt.tzinfo is None:
                    deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
                days_until = (deadline_dt - now).days
                if 0 <= days_until <= 14:
                    score += 0.4  # Quarter review approaching
                elif 14 < days_until <= 30:
                    score += 0.2
            except (ValueError, TypeError):
                pass
    # Deadline urgency: closer deadline = higher urgency
    elif opp.deadline:
        try:
            deadline_dt = datetime.fromisoformat(opp.deadline)
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
            days_until = (deadline_dt - now).days
            if 0 <= days_until <= 7:
                score += 1.0  # Very urgent
            elif 7 < days_until <= 14:
                score += 0.7
            elif 14 < days_until <= 30:
                score += 0.4
            elif 30 < days_until <= 60:
                score += 0.2
        except (ValueError, TypeError):
            pass

    # Recency: recently posted = boost
    if opp.fetched_at:
        try:
            fetched = opp.fetched_at
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            days_old = (now - fetched).days
            if days_old <= 3:
                score += 0.5
            elif days_old <= 7:
                score += 0.3
            elif days_old <= 14:
                score += 0.15
        except (ValueError, TypeError):
            pass

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _to_internal_opp(opp: Opportunity) -> InternalOpportunity:
    """Convert platform ORM Opportunity to internal dataclass for scoring."""
    return InternalOpportunity(
        source=opp.source,
        source_id=opp.source_id,
        title=opp.title,
        description=opp.description or "",
        url=opp.url or "",
        source_type=opp.source_type or "government",
        summary=opp.summary or "",
        opportunity_status=opp.opportunity_status or "open",
        resource_type=getattr(opp, 'resource_type', None),
        resource_provider=getattr(opp, 'resource_provider', None),
        resource_scale=getattr(opp, 'resource_scale', None),
        allocation_details=getattr(opp, 'allocation_details', None),
        eligibility=getattr(opp, 'eligibility', None),
        access_url=getattr(opp, 'access_url', None),
    )


async def score_opportunity_for_user(
    db: AsyncSession, user_id, opportunity: Opportunity, user: Optional[User] = None,
) -> UserOpportunityScore:
    """Score a single opportunity using the multi-signal algorithm."""
    config, weights_map = await build_filter_config(db, user_id)
    kf = KeywordFilter(config)

    internal_opp = _to_internal_opp(opportunity)

    # Hard gate: if exclusion pattern matches, force score to 0.0
    if kf.is_excluded(internal_opp):
        result = await db.execute(
            select(UserOpportunityScore).where(
                UserOpportunityScore.user_id == user_id,
                UserOpportunityScore.opportunity_id == opportunity.id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.relevance_score = 0.0
            existing.keyword_score = 0.0
            existing.profile_score = 0.0
            existing.behavior_score = 0.0
            existing.urgency_score = 0.0
            existing.matched_keywords = []
            return existing
        excluded_score = UserOpportunityScore(
            user_id=user_id,
            opportunity_id=opportunity.id,
            relevance_score=0.0,
            keyword_score=0.0,
            profile_score=0.0,
            behavior_score=0.0,
            urgency_score=0.0,
            matched_keywords=[],
        )
        db.add(excluded_score)
        await db.flush()
        return excluded_score

    matched = kf.extract_matching_keywords(internal_opp)

    # Signal 1: Keyword
    keyword_score = _compute_keyword_score(kf, internal_opp, weights_map)

    # Signal 2: Profile
    if user is None:
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
    opp_text = f"{opportunity.title} {opportunity.description or ''} {opportunity.summary or ''}"
    profile_score = _compute_profile_score(user, opp_text) if user else 0.0

    # Signal 3: Behavioral
    behavior_score = await _compute_behavior_score(db, user_id, opportunity, matched)

    # Signal 4: Urgency
    urgency_score = _compute_urgency_score(opportunity)

    # Combined score
    final_score = (
        W_KEYWORD * keyword_score
        + W_PROFILE * profile_score
        + W_BEHAVIOR * behavior_score
        + W_URGENCY * urgency_score
    )
    final_score = min(final_score, 1.0)

    # Upsert the score
    result = await db.execute(
        select(UserOpportunityScore).where(
            UserOpportunityScore.user_id == user_id,
            UserOpportunityScore.opportunity_id == opportunity.id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.relevance_score = final_score
        existing.keyword_score = keyword_score
        existing.profile_score = profile_score
        existing.behavior_score = behavior_score
        existing.urgency_score = urgency_score
        existing.matched_keywords = matched
        return existing

    user_score = UserOpportunityScore(
        user_id=user_id,
        opportunity_id=opportunity.id,
        relevance_score=final_score,
        keyword_score=keyword_score,
        profile_score=profile_score,
        behavior_score=behavior_score,
        urgency_score=urgency_score,
        matched_keywords=matched,
    )
    db.add(user_score)
    await db.flush()
    return user_score


async def score_all_opportunities_for_user(db: AsyncSession, user_id) -> int:
    """Score all opportunities for a user using the multi-signal algorithm.

    Returns count of scored items.
    """
    config, weights_map = await build_filter_config(db, user_id)
    kf = KeywordFilter(config)

    # Load user for profile matching
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()

    result = await db.execute(select(Opportunity))
    opportunities = result.scalars().all()

    count = 0
    for opp in opportunities:
        internal_opp = _to_internal_opp(opp)
        matched = kf.extract_matching_keywords(internal_opp)

        keyword_score = _compute_keyword_score(kf, internal_opp, weights_map)
        opp_text = f"{opp.title} {opp.description or ''} {opp.summary or ''}"
        profile_score = _compute_profile_score(user, opp_text) if user else 0.0
        behavior_score = await _compute_behavior_score(db, user_id, opp, matched)
        urgency_score = _compute_urgency_score(opp)

        final_score = min(
            W_KEYWORD * keyword_score
            + W_PROFILE * profile_score
            + W_BEHAVIOR * behavior_score
            + W_URGENCY * urgency_score,
            1.0,
        )

        score_result = await db.execute(
            select(UserOpportunityScore).where(
                UserOpportunityScore.user_id == user_id,
                UserOpportunityScore.opportunity_id == opp.id,
            )
        )
        existing = score_result.scalar_one_or_none()
        if existing:
            existing.relevance_score = final_score
            existing.keyword_score = keyword_score
            existing.profile_score = profile_score
            existing.behavior_score = behavior_score
            existing.urgency_score = urgency_score
            existing.matched_keywords = matched
        else:
            db.add(UserOpportunityScore(
                user_id=user_id,
                opportunity_id=opp.id,
                relevance_score=final_score,
                keyword_score=keyword_score,
                profile_score=profile_score,
                behavior_score=behavior_score,
                urgency_score=urgency_score,
                matched_keywords=matched,
            ))
        count += 1

    await db.flush()
    return count

"""Data models for funding opportunities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional


# Standard quarter end dates (month, day)
_QUARTER_ENDS = [(3, 31), (6, 30), (9, 30), (12, 31)]


def next_quarter_deadline(from_date: date | None = None) -> str:
    """Return the next quarter-end date as ISO string (YYYY-MM-DD).

    Standard quarters: Mar 31, Jun 30, Sep 30, Dec 31.
    """
    if from_date is None:
        from_date = date.today()
    for month, day in _QUARTER_ENDS:
        qend = date(from_date.year, month, day)
        if qend >= from_date:
            return qend.isoformat()
    # Past Dec 31 this year → next year Q1
    return date(from_date.year + 1, 3, 31).isoformat()


@dataclass(frozen=True)
class Opportunity:
    """A funding opportunity from any source.

    Attributes:
        source: Origin source name (e.g., 'sam_gov', 'nsf', 'nvidia').
        source_id: Unique ID within the source.
        title: Opportunity title.
        description: Full description text.
        url: Direct link to the opportunity.
        source_type: 'government' or 'industry'.
        deadline: Application deadline, if known.
        posted_date: Date the opportunity was posted.
        funding_amount: Funding amount as text (e.g., "$500K", "Up to $1M").
        keywords: Extracted keywords from the opportunity.
        relevance_score: Computed relevance score (0.0-1.0).
        summary: LLM-generated summary.
    """

    source: str
    source_id: str
    title: str
    description: str
    url: str
    source_type: str = "government"
    deadline: Optional[datetime] = None
    posted_date: Optional[datetime] = None
    funding_amount: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    relevance_score: float = 0.0
    summary: str = ""
    opportunity_status: str = "open"  # "open", "coming_soon", "closed"
    deadline_type: str = "fixed"  # "fixed", "rolling", "quarterly", "none"
    # Compute resource fields (for source_type='compute')
    resource_type: Optional[str] = None  # gpu, tpu, hpc, cloud_credits, hardware_grant
    resource_provider: Optional[str] = None  # NSF ACCESS, NVIDIA, AWS, DOE, etc.
    resource_scale: Optional[str] = None  # small, medium, large, credits
    allocation_details: Optional[str] = None  # "Up to 30,000 H100 GPU-hours"
    eligibility: Optional[str] = None  # "Faculty PI", "Any researcher"
    access_url: Optional[str] = None  # Direct application portal URL

    @property
    def composite_id(self) -> str:
        """Unique identifier across all sources."""
        return f"{self.source}_{self.source_id}"

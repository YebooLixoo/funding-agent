"""Data models for funding opportunities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


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

    @property
    def composite_id(self) -> str:
        """Unique identifier across all sources."""
        return f"{self.source}_{self.source_id}"

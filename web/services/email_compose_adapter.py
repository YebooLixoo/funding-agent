from __future__ import annotations
from collections import defaultdict


def group_by_source_type(rows) -> dict:
    """Group (Opportunity, UserOpportunityScore | None) tuples into the
    dict-of-lists shape that src/emailer.Emailer.compose() expects.

    Output keys: '{source_type}_opps' (e.g., 'government_opps', 'industry_opps',
    'university_opps', 'compute_opps'). Missing source_type defaults to 'government'.
    """
    buckets: dict[str, list[dict]] = defaultdict(list)
    for opp, score in rows:
        d = {
            "composite_id": opp.composite_id,
            "title": opp.title,
            "url": opp.url,
            "deadline": opp.deadline,
            "posted_date": getattr(opp, "posted_date", None),
            "deadline_type": getattr(opp, "deadline_type", "fixed"),
            "opportunity_status": getattr(opp, "opportunity_status", "open"),
            "summary": opp.summary,
            "funding_amount": opp.funding_amount,
            "source": opp.source,
            "source_type": opp.source_type,
            "relevance_score": (score.relevance_score if score is not None else None),
            "resource_type": getattr(opp, "resource_type", None),
            "resource_provider": getattr(opp, "resource_provider", None),
            "resource_scale": getattr(opp, "resource_scale", None),
            "allocation_details": getattr(opp, "allocation_details", None),
            "eligibility": getattr(opp, "eligibility", None),
            "access_url": getattr(opp, "access_url", None),
        }
        key = f"{opp.source_type or 'government'}_opps"
        buckets[key].append(d)
    return dict(buckets)

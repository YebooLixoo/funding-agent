"""HistoryDataSource protocol + PlatformDBSource adapter.

Decouples ``src.history_generator.HistoryGenerator`` from ``src.state.StateDB``
so the same generator can render pages from either the legacy SQLite state DB
or the platform's SQLAlchemy ORM.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.models.opportunity import Opportunity
from web.models.user import User
from web.models.user_email_delivery import UserEmailDelivery


class HistoryDataSource(Protocol):
    """Minimal interface ``src.history_generator.HistoryGenerator`` depends on."""

    def get_emailed_opportunities(self) -> list[dict]: ...


class PlatformDBSource:
    """Sync facade wrapping pre-fetched dict rows.

    Build the rows ahead of time from an async caller (e.g., via
    :func:`fetch_admin_emailed_opportunities`), then pass into the generator.
    """

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def get_emailed_opportunities(self) -> list[dict]:
        return self._rows


async def fetch_admin_emailed_opportunities(
    db: AsyncSession, admin_email: str
) -> list[dict]:
    """Return all opportunities ever delivered to the admin user, newest first.

    Used by the static history page generator. Returns dicts in the shape
    ``src.history_generator`` and ``templates/history.html`` expect.
    """
    admin = (
        await db.execute(
            select(User).where(User.email == admin_email, User.is_admin.is_(True))
        )
    ).scalar_one()

    q = (
        select(Opportunity, UserEmailDelivery.sent_at)
        .join(UserEmailDelivery, UserEmailDelivery.opportunity_id == Opportunity.id)
        .where(UserEmailDelivery.user_id == admin.id)
        .order_by(UserEmailDelivery.sent_at.desc())
    )
    result = (await db.execute(q)).all()
    return [_to_dict(opp, sent_at) for opp, sent_at in result]


def _to_dict(o: Opportunity, sent_at=None) -> dict:
    """Map an ORM Opportunity into the dict shape ``templates/history.html`` expects.

    ``sent_at`` (when available) is exposed as ``fetched_at`` so the generator's
    month-grouping logic continues to work.
    """
    fetched_at = sent_at if sent_at is not None else o.fetched_at
    return {
        "composite_id": o.composite_id,
        "title": o.title,
        "url": o.url,
        "deadline": o.deadline,
        "posted_date": o.posted_date,
        "summary": o.summary,
        "funding_amount": o.funding_amount,
        "source": o.source,
        "source_type": o.source_type or "government",
        "deadline_type": o.deadline_type or "fixed",
        "opportunity_status": o.opportunity_status or "open",
        "resource_type": o.resource_type,
        "resource_provider": o.resource_provider,
        "resource_scale": o.resource_scale,
        "allocation_details": o.allocation_details,
        "eligibility": o.eligibility,
        "access_url": o.access_url,
        "fetched_at": fetched_at.isoformat() if hasattr(fetched_at, "isoformat") else fetched_at,
    }

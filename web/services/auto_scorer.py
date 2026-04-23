"""Auto-scoring orchestration: score newly-fetched opportunities for active users.

Called by ``fetch_runner`` after new opportunities are written. Without this
step, per-user digests find nothing to send.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.models.user import User
from web.services.scoring import score_opportunities_for_user

logger = logging.getLogger(__name__)


async def score_new_opportunities(
    db: AsyncSession, opportunity_ids: list[uuid.UUID]
) -> None:
    """Compute UserOpportunityScore for each active user x given opportunities.

    Idempotent at the per-user level: ``score_opportunity_for_user`` upserts.
    Per-user failures are logged but do not fail the batch.
    """
    if not opportunity_ids:
        return

    users = (
        await db.execute(select(User).where(User.is_active.is_(True)))
    ).scalars().all()

    for user in users:
        try:
            await score_opportunities_for_user(db, user.id, opportunity_ids)
        except Exception:
            logger.exception("auto_scorer: failed for user %s", user.id)

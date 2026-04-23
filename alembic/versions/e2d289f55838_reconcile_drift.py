"""reconcile drift

Add columns the live ``data/platform.db`` was missing relative to the ORM:

  * ``opportunities``: opportunity_status, deadline_type, plus the
    resource_* fields (resource_type, resource_provider, resource_scale,
    allocation_details, eligibility, access_url).
  * ``user_opportunity_scores``: keyword_score, profile_score,
    behavior_score, urgency_score, view_count, clicked_at.

Each ``op.add_column`` is wrapped in an existence check so the migration is
idempotent: on a fresh install the baseline already created these columns
(they are part of the current ORM), so this revision becomes a no-op; on
the live DB the baseline was stamped (never actually run), so the columns
genuinely need to be added here.

Revision ID: e2d289f55838
Revises: 58b957aa7ad0
Create Date: 2026-04-16 22:13:10.592694
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "e2d289f55838"
down_revision: Union[str, None] = "58b957aa7ad0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _add_if_missing(table: str, column: sa.Column) -> None:
    if not _has_column(table, column.name):
        op.add_column(table, column)


def upgrade() -> None:
    # opportunities: status + deadline classification
    _add_if_missing(
        "opportunities",
        sa.Column(
            "opportunity_status",
            sa.String(length=32),
            server_default="open",
            nullable=False,
        ),
    )
    _add_if_missing(
        "opportunities",
        sa.Column(
            "deadline_type",
            sa.String(length=32),
            server_default="fixed",
            nullable=False,
        ),
    )

    # opportunities: compute-resource fields
    _add_if_missing(
        "opportunities",
        sa.Column("resource_type", sa.String(length=64), nullable=True),
    )
    _add_if_missing(
        "opportunities",
        sa.Column("resource_provider", sa.String(length=128), nullable=True),
    )
    _add_if_missing(
        "opportunities",
        sa.Column("resource_scale", sa.String(length=32), nullable=True),
    )
    _add_if_missing(
        "opportunities",
        sa.Column("allocation_details", sa.String(length=512), nullable=True),
    )
    _add_if_missing(
        "opportunities",
        sa.Column("eligibility", sa.String(length=256), nullable=True),
    )
    _add_if_missing(
        "opportunities",
        sa.Column("access_url", sa.String(length=2048), nullable=True),
    )

    # user_opportunity_scores: granular score components + view tracking
    _add_if_missing(
        "user_opportunity_scores",
        sa.Column("keyword_score", sa.Float(), nullable=True),
    )
    _add_if_missing(
        "user_opportunity_scores",
        sa.Column("profile_score", sa.Float(), nullable=True),
    )
    _add_if_missing(
        "user_opportunity_scores",
        sa.Column("behavior_score", sa.Float(), nullable=True),
    )
    _add_if_missing(
        "user_opportunity_scores",
        sa.Column("urgency_score", sa.Float(), nullable=True),
    )
    _add_if_missing(
        "user_opportunity_scores",
        sa.Column(
            "view_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    _add_if_missing(
        "user_opportunity_scores",
        sa.Column(
            "clicked_at", sa.DateTime(timezone=True), nullable=True
        ),
    )


def _drop_if_exists(table: str, column: str) -> None:
    if _has_column(table, column):
        op.drop_column(table, column)


def downgrade() -> None:
    _drop_if_exists("user_opportunity_scores", "clicked_at")
    _drop_if_exists("user_opportunity_scores", "view_count")
    _drop_if_exists("user_opportunity_scores", "urgency_score")
    _drop_if_exists("user_opportunity_scores", "behavior_score")
    _drop_if_exists("user_opportunity_scores", "profile_score")
    _drop_if_exists("user_opportunity_scores", "keyword_score")

    _drop_if_exists("opportunities", "access_url")
    _drop_if_exists("opportunities", "eligibility")
    _drop_if_exists("opportunities", "allocation_details")
    _drop_if_exists("opportunities", "resource_scale")
    _drop_if_exists("opportunities", "resource_provider")
    _drop_if_exists("opportunities", "resource_type")
    _drop_if_exists("opportunities", "deadline_type")
    _drop_if_exists("opportunities", "opportunity_status")

"""reconcile drift

Add columns the live ``data/platform.db`` was missing relative to the ORM:

  * ``opportunities``: opportunity_status, deadline_type, plus the
    resource_* fields (resource_type, resource_provider, resource_scale,
    allocation_details, eligibility, access_url).
  * ``user_opportunity_scores``: keyword_score, profile_score,
    behavior_score, urgency_score, view_count, clicked_at.

Revision ID: e2d289f55838
Revises: 1466071c64e1
Create Date: 2026-04-16 22:13:10.592694
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2d289f55838"
down_revision: Union[str, None] = "1466071c64e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # opportunities: status + deadline classification
    op.add_column(
        "opportunities",
        sa.Column(
            "opportunity_status",
            sa.String(length=32),
            server_default="open",
            nullable=False,
        ),
    )
    op.add_column(
        "opportunities",
        sa.Column(
            "deadline_type",
            sa.String(length=32),
            server_default="fixed",
            nullable=False,
        ),
    )

    # opportunities: compute-resource fields
    op.add_column(
        "opportunities",
        sa.Column("resource_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("resource_provider", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("resource_scale", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("allocation_details", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("eligibility", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("access_url", sa.String(length=2048), nullable=True),
    )

    # user_opportunity_scores: granular score components + view tracking
    op.add_column(
        "user_opportunity_scores",
        sa.Column("keyword_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "user_opportunity_scores",
        sa.Column("profile_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "user_opportunity_scores",
        sa.Column("behavior_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "user_opportunity_scores",
        sa.Column("urgency_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "user_opportunity_scores",
        sa.Column(
            "view_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "user_opportunity_scores",
        sa.Column(
            "clicked_at", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("user_opportunity_scores", "clicked_at")
    op.drop_column("user_opportunity_scores", "view_count")
    op.drop_column("user_opportunity_scores", "urgency_score")
    op.drop_column("user_opportunity_scores", "behavior_score")
    op.drop_column("user_opportunity_scores", "profile_score")
    op.drop_column("user_opportunity_scores", "keyword_score")

    op.drop_column("opportunities", "access_url")
    op.drop_column("opportunities", "eligibility")
    op.drop_column("opportunities", "allocation_details")
    op.drop_column("opportunities", "resource_scale")
    op.drop_column("opportunities", "resource_provider")
    op.drop_column("opportunities", "resource_type")
    op.drop_column("opportunities", "deadline_type")
    op.drop_column("opportunities", "opportunity_status")

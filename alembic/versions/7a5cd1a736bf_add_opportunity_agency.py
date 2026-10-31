"""add opportunity agency

Adds ``opportunities.agency`` (issuing agency code, e.g. ``DOT-FHWA``). The live
``data/platform.db`` already has this column — it was added outside alembic in
March 2026 — so, like ``e2d289f55838``, both directions are guarded for
idempotency: a no-op on the live DB, a real ``ADD COLUMN`` on fresh installs.

Revision ID: 7a5cd1a736bf
Revises: 52886e4f11fd
Create Date: 2026-10-31 17:03:08.824921
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '7a5cd1a736bf'
down_revision: Union[str, None] = '52886e4f11fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_agency() -> bool:
    columns = inspect(op.get_bind()).get_columns("opportunities")
    return "agency" in {c["name"] for c in columns}


def upgrade() -> None:
    if not _has_agency():
        op.add_column("opportunities", sa.Column("agency", sa.String(length=128), nullable=True))


def downgrade() -> None:
    if _has_agency():
        op.drop_column("opportunities", "agency")

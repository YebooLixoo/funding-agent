"""baseline

Snapshot anchor representing the schema as captured from the live SQLite
``data/platform.db`` at the time alembic became the authoritative schema
source. The live DB is stamped at this revision via ``alembic stamp`` so
that subsequent migrations (starting with the drift-reconciliation
revision) can apply cleanly.

For greenfield databases this revision is a no-op; the drift-reconciliation
revision and any future revisions handle the actual DDL. (We deliberately
do not encode CREATE TABLE statements here because mixing those with the
follow-up add_column drift migration would produce duplicate-column errors
on fresh runs.)

Revision ID: 1466071c64e1
Revises:
Create Date: 2026-04-16 22:12:24.313676
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "1466071c64e1"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

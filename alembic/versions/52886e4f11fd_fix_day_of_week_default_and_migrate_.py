"""fix day_of_week default and migrate existing rows

Revision ID: 52886e4f11fd
Revises: 4714f5d96165
Create Date: 2026-04-22 21:11:56.609164
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52886e4f11fd'
down_revision: Union[str, None] = '4714f5d96165'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows had day_of_week=4 from a buggy default that confused launchd
    # weekday semantics (0=Sun..6=Sat) with Python's datetime.weekday() (0=Mon..6=Sun).
    # The intent was Thursday; under Python weekday() that is 3, not 4. Fix the rows
    # so the email scheduler actually fires on Thursday.
    op.execute("UPDATE user_email_prefs SET day_of_week = 3 WHERE day_of_week = 4")


def downgrade() -> None:
    op.execute("UPDATE user_email_prefs SET day_of_week = 4 WHERE day_of_week = 3")

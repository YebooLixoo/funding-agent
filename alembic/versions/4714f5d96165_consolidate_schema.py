"""consolidate schema

Revision ID: 4714f5d96165
Revises: e2d289f55838
Create Date: 2026-04-22 20:19:22.111854
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4714f5d96165'
down_revision: Union[str, None] = 'e2d289f55838'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fetch_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source', sa.String(length=64), nullable=False),
        sa.Column('fetch_window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fetch_window_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('error_msg', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'source_bootstrap',
        sa.Column('source_name', sa.String(length=64), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('bootstrapped_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('source_name'),
    )
    op.create_table(
        'broadcast_recipients',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_user_id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('unsubscribe_token', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('unsubscribed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_user_id', 'email', name='uq_broadcast_owner_email'),
        sa.UniqueConstraint('unsubscribe_token'),
    )
    op.create_index(
        op.f('ix_broadcast_recipients_owner_user_id'),
        'broadcast_recipients',
        ['owner_user_id'],
        unique=False,
    )
    op.create_table(
        'system_filter_keywords',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('keyword', sa.String(length=256), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('source_user_id', sa.UUID(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['source_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('keyword', 'category', 'source_user_id', name='uq_sfk_kw_cat_user'),
    )
    op.create_table(
        'system_search_terms',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('term', sa.String(length=256), nullable=False),
        sa.Column('target_source', sa.String(length=64), nullable=False),
        sa.Column('source_user_id', sa.UUID(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['source_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('term', 'target_source', 'source_user_id', name='uq_sst_term_src_user'),
    )
    op.create_index(
        'ix_sst_target_active',
        'system_search_terms',
        ['target_source', 'is_active'],
        unique=False,
    )
    op.create_table(
        'user_email_deliveries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('opportunity_id', sa.UUID(), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'opportunity_id', name='uq_user_opp_delivery'),
    )
    op.create_index(
        'ix_user_email_deliveries_user_sent',
        'user_email_deliveries',
        ['user_id', 'sent_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_user_email_deliveries_user_sent', table_name='user_email_deliveries')
    op.drop_table('user_email_deliveries')
    op.drop_index('ix_sst_target_active', table_name='system_search_terms')
    op.drop_table('system_search_terms')
    op.drop_table('system_filter_keywords')
    op.drop_index(op.f('ix_broadcast_recipients_owner_user_id'), table_name='broadcast_recipients')
    op.drop_table('broadcast_recipients')
    op.drop_table('source_bootstrap')
    op.drop_table('fetch_history')

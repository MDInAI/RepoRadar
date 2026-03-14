"""add obsession contexts

Revision ID: 20260313_0025
Revises: 20260312_0024
Create Date: 2026-03-13 23:14:13.340000

"""
from alembic import op
import sqlalchemy as sa


revision = '20260313_0025'
down_revision = '20260312_0024'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'obsession_context',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('idea_family_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('active', 'paused', 'completed', name='obsession_context_status', create_constraint=True), nullable=False, server_default='active'),
        sa.Column('refresh_policy', sa.Enum('manual', 'daily', 'weekly', name='obsession_refresh_policy', create_constraint=True), nullable=False, server_default='manual'),
        sa.Column('last_refresh_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))")),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))")),
        sa.CheckConstraint("title != ''", name='ck_obsession_context_title_not_blank'),
        sa.ForeignKeyConstraint(['idea_family_id'], ['idea_family.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_obsession_context_idea_family_id', 'obsession_context', ['idea_family_id'])
    op.create_index('ix_obsession_context_status', 'obsession_context', ['status'])


def downgrade() -> None:
    op.drop_index('ix_obsession_context_status', table_name='obsession_context')
    op.drop_index('ix_obsession_context_idea_family_id', table_name='obsession_context')
    op.drop_table('obsession_context')

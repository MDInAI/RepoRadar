"""add agent_pause_state version column

Revision ID: 20260312_0021
Revises: 20260311_0020
Create Date: 2026-03-12

"""
from alembic import op
import sqlalchemy as sa

revision = '20260312_0021'
down_revision = '20260311_0020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('agent_pause_state', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('agent_pause_state', 'version')

"""add synthesis run obsession fk

Revision ID: 20260313_0026
Revises: 20260313_0025
Create Date: 2026-03-13 23:14:23.340000

"""
from alembic import op
import sqlalchemy as sa


revision = '20260313_0026'
down_revision = '20260313_0025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('synthesis_run', sa.Column('obsession_context_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_synthesis_run_obsession_context_id', 'synthesis_run', 'obsession_context', ['obsession_context_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_synthesis_run_obsession_context_id', 'synthesis_run', ['obsession_context_id'])


def downgrade() -> None:
    op.drop_index('ix_synthesis_run_obsession_context_id', table_name='synthesis_run')
    op.drop_constraint('fk_synthesis_run_obsession_context_id', 'synthesis_run', type_='foreignkey')
    op.drop_column('synthesis_run', 'obsession_context_id')

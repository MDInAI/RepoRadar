"""add synthesis runs

Revision ID: 20260312_0023
Revises: 20260312_0022
Create Date: 2026-03-12 19:33:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260312_0023'
down_revision = '20260312_0022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'synthesis_run',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('idea_family_id', sa.Integer(), nullable=True),
        sa.Column('run_type', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), server_default=sa.text("'pending'"), nullable=False),
        sa.Column('input_repository_ids', sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column('output_text', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"), nullable=False),
        sa.CheckConstraint("run_type IN ('combiner', 'obsession')", name='ck_synthesis_run_type_valid'),
        sa.ForeignKeyConstraint(['idea_family_id'], ['idea_family.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index('ix_synthesis_run_idea_family_id', 'synthesis_run', ['idea_family_id'], unique=False)
    op.create_index('ix_synthesis_run_status', 'synthesis_run', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_synthesis_run_status', table_name='synthesis_run')
    op.drop_index('ix_synthesis_run_idea_family_id', table_name='synthesis_run')
    op.drop_table('synthesis_run')

"""add agent memory segments

Revision ID: 20260314_0028
Revises: 20260314_0027
Create Date: 2026-03-14 01:22:22.442000

"""
from alembic import op
import sqlalchemy as sa


revision = '20260314_0028'
down_revision = '20260314_0027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agent_memory_segments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('obsession_context_id', sa.Integer(), nullable=False),
        sa.Column('segment_key', sa.String(length=100), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_type', sa.String(length=32), server_default=sa.text("'markdown'"), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"), nullable=False),
        sa.CheckConstraint("segment_key != ''", name='ck_agent_memory_segment_key_not_blank'),
        sa.CheckConstraint("content != ''", name='ck_agent_memory_content_not_blank'),
        sa.ForeignKeyConstraint(['obsession_context_id'], ['obsession_context.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('obsession_context_id', 'segment_key', name='uq_agent_memory_segments_obsession_context_id_segment_key')
    )
    op.create_index('ix_agent_memory_segments_obsession_context_id', 'agent_memory_segments', ['obsession_context_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_agent_memory_segments_obsession_context_id', table_name='agent_memory_segments')
    op.drop_table('agent_memory_segments')

"""add memory constraints

Revision ID: 20260314_0029
Revises: 20260314_0028
Create Date: 2026-03-14 02:14:24.790000

"""
from alembic import op


revision = '20260314_0029'
down_revision = '20260314_0028'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        'ck_agent_memory_content_type_enum',
        'agent_memory_segments',
        "content_type IN ('markdown', 'json')"
    )
    op.create_check_constraint(
        'ck_agent_memory_content_size',
        'agent_memory_segments',
        'length(content) <= 51200'
    )


def downgrade() -> None:
    op.drop_constraint('ck_agent_memory_content_size', 'agent_memory_segments', type_='check')
    op.drop_constraint('ck_agent_memory_content_type_enum', 'agent_memory_segments', type_='check')

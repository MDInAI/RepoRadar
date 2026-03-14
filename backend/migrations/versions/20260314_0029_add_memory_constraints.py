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
    with op.batch_alter_table("agent_memory_segments") as batch_op:
        batch_op.create_check_constraint(
            "ck_agent_memory_content_type_enum",
            "content_type IN ('markdown', 'json')",
        )
        batch_op.create_check_constraint(
            "ck_agent_memory_content_size",
            "length(content) <= 51200",
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_memory_segments") as batch_op:
        batch_op.drop_constraint("ck_agent_memory_content_size", type_="check")
        batch_op.drop_constraint("ck_agent_memory_content_type_enum", type_="check")

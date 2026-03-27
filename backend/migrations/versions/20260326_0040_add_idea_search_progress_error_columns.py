"""add error tracking columns to idea_search_progress

Revision ID: 20260326_0040
Revises: 20260326_0039
Create Date: 2026-03-26 00:00:00.000000

Add consecutive_errors and last_error columns so the worker can track
persistent GitHub API failures per query and skip windows that always fail.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260326_0040"
down_revision = "20260326_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("idea_search_progress") as batch_op:
        batch_op.add_column(
            sa.Column("consecutive_errors", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )
        batch_op.add_column(
            sa.Column("last_error", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("idea_search_progress") as batch_op:
        batch_op.drop_column("last_error")
        batch_op.drop_column("consecutive_errors")

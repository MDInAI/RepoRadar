"""add analyst_enabled to idea_search

Revision ID: 20260327_0042
Revises: 20260327_0041
Create Date: 2026-03-27 00:00:00.000000

Allows the user to opt specific IdeaSearches into analyst processing,
bypassing the triage gate so Scout-discovered repos get scored and tagged.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260327_0042"
down_revision = "20260327_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("idea_search") as batch_op:
        batch_op.add_column(
            sa.Column("analyst_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )


def downgrade() -> None:
    with op.batch_alter_table("idea_search") as batch_op:
        batch_op.drop_column("analyst_enabled")

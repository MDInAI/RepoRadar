"""add query_index and query_text to idea_search_discovery

Revision ID: 20260327_0041
Revises: 20260326_0040
Create Date: 2026-03-27 00:00:00.000000

Records which query within an IdeaSearch discovered each repository so that
the UI can show "found by search X, query Y: <query text>" on each repo.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260327_0041"
down_revision = "20260326_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("idea_search_discovery") as batch_op:
        batch_op.add_column(
            sa.Column("query_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )
        batch_op.add_column(
            sa.Column("query_text", sa.Text(), nullable=False, server_default=sa.text("''")),
        )


def downgrade() -> None:
    with op.batch_alter_table("idea_search_discovery") as batch_op:
        batch_op.drop_column("query_text")
        batch_op.drop_column("query_index")

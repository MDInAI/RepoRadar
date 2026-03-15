"""add remaining llm analysis fields

Revision ID: 20260316_0035
Revises: 20260315_0034
Create Date: 2026-03-16 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260316_0035"
down_revision = "20260315_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "repository_analysis_result",
        sa.Column(
            "suggested_new_categories",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "repository_analysis_result",
        sa.Column(
            "suggested_new_tags",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "repository_analysis_result",
        sa.Column("confidence_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "repository_analysis_result",
        sa.Column("recommended_action", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("repository_analysis_result", "recommended_action")
    op.drop_column("repository_analysis_result", "confidence_score")
    op.drop_column("repository_analysis_result", "suggested_new_tags")
    op.drop_column("repository_analysis_result", "suggested_new_categories")

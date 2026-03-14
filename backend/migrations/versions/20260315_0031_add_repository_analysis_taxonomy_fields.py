"""add repository analysis taxonomy fields

Revision ID: 20260315_0031
Revises: 20260315_0030
Create Date: 2026-03-15 13:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260315_0031"
down_revision: str | None = "20260315_0030"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("repository_analysis_result")
    }

    if "category" not in existing_columns:
        op.add_column(
            "repository_analysis_result",
            sa.Column(
                "category",
                sa.Enum(
                    "workflow",
                    "analytics",
                    "devops",
                    "infrastructure",
                    "devtools",
                    "crm",
                    "communication",
                    "support",
                    "observability",
                    "low_code",
                    "security",
                    "ai_ml",
                    "data",
                    "productivity",
                    name="repository_category",
                    native_enum=False,
                    create_constraint=True,
                ),
                nullable=True,
            ),
        )
    if "agent_tags" not in existing_columns:
        op.add_column(
            "repository_analysis_result",
            sa.Column(
                "agent_tags",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("repository_analysis_result")
    }

    if "agent_tags" in existing_columns:
        op.drop_column("repository_analysis_result", "agent_tags")
    if "category" in existing_columns:
        op.drop_column("repository_analysis_result", "category")

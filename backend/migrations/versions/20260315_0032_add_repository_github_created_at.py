"""add repository github created at

Revision ID: 20260315_0032
Revises: 20260315_0031
Create Date: 2026-03-15 11:05:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260315_0032"
down_revision = "20260315_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "repository_intake",
        sa.Column("github_created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("repository_intake", "github_created_at")

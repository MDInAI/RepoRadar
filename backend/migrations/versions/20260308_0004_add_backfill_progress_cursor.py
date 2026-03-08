"""add backfill progress cursor

Revision ID: 20260308_0004
Revises: 20260308_0003
Create Date: 2026-03-08 13:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260308_0004"
down_revision: str | None = "20260308_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "backfill_progress",
        sa.Column("created_before_cursor", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("backfill_progress", "created_before_cursor")

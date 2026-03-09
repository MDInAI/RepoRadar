"""add backfill resume_required

Revision ID: 20260308_0006
Revises: 20260308_0005
Create Date: 2026-03-08 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260308_0006"
down_revision: str | None = "20260308_0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "backfill_progress",
        sa.Column("resume_required", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.execute(
        sa.text(
            """
            UPDATE backfill_progress
            SET resume_required = CASE
                WHEN exhausted = 1 THEN 0
                ELSE 1
            END
            """
        )
    )


def downgrade() -> None:
    op.drop_column("backfill_progress", "resume_required")

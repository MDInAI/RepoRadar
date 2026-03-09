"""add progress run page counters

Revision ID: 20260308_0007
Revises: 20260308_0006
Create Date: 2026-03-08 19:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260308_0007"
down_revision: str | None = "20260308_0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "backfill_progress",
        sa.Column(
            "pages_processed_in_run",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "firehose_progress",
        sa.Column(
            "pages_processed_in_run",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.execute(
        sa.text(
            """
            UPDATE backfill_progress
            SET pages_processed_in_run = CASE
                WHEN resume_required = 1 THEN CASE
                    WHEN next_page > 1 THEN next_page - 1
                    ELSE 0
                END
                ELSE 0
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE firehose_progress
            SET pages_processed_in_run = CASE
                WHEN resume_required = 1 THEN CASE
                    WHEN next_page > 1 THEN next_page - 1
                    ELSE 0
                END
                ELSE 0
            END
            """
        )
    )


def downgrade() -> None:
    op.drop_column("firehose_progress", "pages_processed_in_run")
    op.drop_column("backfill_progress", "pages_processed_in_run")

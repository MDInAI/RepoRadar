"""add backfill progress table

Revision ID: 20260308_0003
Revises: 20260307_0002
Create Date: 2026-03-08 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260308_0003"
down_revision: str | None = "20260307_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backfill_progress",
        sa.Column(
            "source_provider",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'github'"),
        ),
        sa.Column("window_start_date", sa.Date(), nullable=False),
        sa.Column("created_before_boundary", sa.Date(), nullable=False),
        sa.Column(
            "next_page",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "exhausted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_checkpointed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
        sa.CheckConstraint(
            "source_provider IN ('github')", name="ck_backfill_progress_source_provider_valid"
        ),
        sa.CheckConstraint("next_page > 0", name="ck_backfill_progress_next_page_positive"),
        sa.CheckConstraint(
            "window_start_date < created_before_boundary",
            name="ck_backfill_progress_window_before_boundary",
        ),
        sa.PrimaryKeyConstraint("source_provider", name="pk_backfill_progress"),
    )


def downgrade() -> None:
    op.drop_table("backfill_progress")

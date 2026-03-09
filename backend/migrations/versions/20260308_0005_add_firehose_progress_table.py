"""add firehose progress table

Revision ID: 20260308_0005
Revises: 20260308_0004
Create Date: 2026-03-08 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260308_0005"
down_revision: str | None = "20260308_0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

firehose_progress_mode = sa.Enum(
    "new",
    "trending",
    name="firehose_progress_mode",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "firehose_progress",
        sa.Column(
            "source_provider",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'github'"),
        ),
        sa.Column("active_mode", firehose_progress_mode, nullable=True),
        sa.Column(
            "next_page",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("new_anchor_date", sa.Date(), nullable=True),
        sa.Column("trending_anchor_date", sa.Date(), nullable=True),
        sa.Column("run_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resume_required",
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
            "source_provider IN ('github')", name="ck_firehose_progress_source_provider_valid"
        ),
        sa.CheckConstraint("next_page > 0", name="ck_firehose_progress_next_page_positive"),
        sa.CheckConstraint(
            "(resume_required = 0) OR ("
            "active_mode IS NOT NULL AND "
            "new_anchor_date IS NOT NULL AND "
            "trending_anchor_date IS NOT NULL AND "
            "run_started_at IS NOT NULL"
            ")",
            name="ck_firehose_progress_resume_state_complete",
        ),
        sa.PrimaryKeyConstraint("source_provider", name="pk_firehose_progress"),
    )


def downgrade() -> None:
    op.drop_table("firehose_progress")

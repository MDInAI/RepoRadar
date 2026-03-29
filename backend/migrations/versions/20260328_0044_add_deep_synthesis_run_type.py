"""add deep_synthesis run type to synthesis_run

Revision ID: 20260328_0044
Revises: 20260327_0043
Create Date: 2026-03-28 00:00:00.000000

Add 'deep_synthesis' to the run_type CHECK constraint on synthesis_run,
enabling the deep comparative synthesis pipeline backed by Claude Opus
with extended thinking.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260328_0044"
down_revision: str | None = "20260327_0043"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("synthesis_run") as batch_op:
        batch_op.drop_constraint("ck_synthesis_run_type_valid", type_="check")
        batch_op.create_check_constraint(
            "ck_synthesis_run_type_valid",
            "run_type IN ('combiner', 'obsession', 'deep_synthesis')",
        )


def downgrade() -> None:
    with op.batch_alter_table("synthesis_run") as batch_op:
        batch_op.drop_constraint("ck_synthesis_run_type_valid", type_="check")
        batch_op.create_check_constraint(
            "ck_synthesis_run_type_valid",
            "run_type IN ('combiner', 'obsession')",
        )

"""fix agent_pause_state datetime columns to timezone-aware

Revision ID: 20260310_0018
Revises: 20260310_0017
Create Date: 2026-03-10 20:00:00.000000

Fix paused_at and resumed_at columns to use DateTime(timezone=True) to match
the UTC-aware datetime contract used by the rest of the operational-event schema.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260310_0018"
down_revision: str | None = "20260310_0017"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_pause_state") as batch_op:
        batch_op.alter_column(
            "paused_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "resumed_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_pause_state") as batch_op:
        batch_op.alter_column(
            "paused_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "resumed_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=True,
        )

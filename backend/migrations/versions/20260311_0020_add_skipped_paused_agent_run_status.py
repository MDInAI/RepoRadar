"""add skipped_paused agent run status

Revision ID: 20260311_0020
Revises: 20260310_0019
Create Date: 2026-03-11 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260311_0020"
down_revision: str | None = "20260310_0019"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_OLD_STATUS_ENUM = sa.Enum(
    "running",
    "completed",
    "failed",
    "skipped",
    name="agent_run_status",
    native_enum=False,
    create_constraint=True,
)
_NEW_STATUS_ENUM = sa.Enum(
    "running",
    "completed",
    "failed",
    "skipped",
    "skipped_paused",
    name="agent_run_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    with op.batch_alter_table("agent_runs", recreate="always") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=_OLD_STATUS_ENUM,
            type_=_NEW_STATUS_ENUM,
            existing_nullable=False,
            existing_server_default=sa.text("'running'"),
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE agent_runs SET status = 'skipped' WHERE status = 'skipped_paused'"
        )
    )
    with op.batch_alter_table("agent_runs", recreate="always") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=_NEW_STATUS_ENUM,
            type_=_OLD_STATUS_ENUM,
            existing_nullable=False,
            existing_server_default=sa.text("'running'"),
        )

"""make agent run item counts nullable

Revision ID: 20260310_0014
Revises: 20260310_0013
Create Date: 2026-03-10 12:00:00.000000

Allow items_processed, items_succeeded, and items_failed to be NULL so that
unexpected mid-run crashes can record a terminal AgentRun row without falsely
asserting specific item counts that were never actually determined.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260310_0014"
down_revision: str | None = "20260310_0013"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.alter_column(
            "items_processed",
            existing_type=sa.Integer(),
            nullable=True,
            existing_server_default=sa.text("0"),
            server_default=None,
        )
        batch_op.alter_column(
            "items_succeeded",
            existing_type=sa.Integer(),
            nullable=True,
            existing_server_default=sa.text("0"),
            server_default=None,
        )
        batch_op.alter_column(
            "items_failed",
            existing_type=sa.Integer(),
            nullable=True,
            existing_server_default=sa.text("0"),
            server_default=None,
        )
        batch_op.drop_constraint("ck_agent_runs_items_processed_non_negative", type_="check")
        batch_op.drop_constraint("ck_agent_runs_items_succeeded_non_negative", type_="check")
        batch_op.drop_constraint("ck_agent_runs_items_failed_non_negative", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_runs_items_processed_non_negative",
            "items_processed IS NULL OR items_processed >= 0",
        )
        batch_op.create_check_constraint(
            "ck_agent_runs_items_succeeded_non_negative",
            "items_succeeded IS NULL OR items_succeeded >= 0",
        )
        batch_op.create_check_constraint(
            "ck_agent_runs_items_failed_non_negative",
            "items_failed IS NULL OR items_failed >= 0",
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE agent_runs
            SET
                items_processed = COALESCE(items_processed, 0),
                items_succeeded = COALESCE(items_succeeded, 0),
                items_failed = COALESCE(items_failed, 0)
            WHERE
                items_processed IS NULL
                OR items_succeeded IS NULL
                OR items_failed IS NULL
            """
        )
    )
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_constraint("ck_agent_runs_items_processed_non_negative", type_="check")
        batch_op.drop_constraint("ck_agent_runs_items_succeeded_non_negative", type_="check")
        batch_op.drop_constraint("ck_agent_runs_items_failed_non_negative", type_="check")
        batch_op.alter_column(
            "items_processed",
            existing_type=sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        )
        batch_op.alter_column(
            "items_succeeded",
            existing_type=sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        )
        batch_op.alter_column(
            "items_failed",
            existing_type=sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        )
        batch_op.create_check_constraint(
            "ck_agent_runs_items_processed_non_negative",
            "items_processed >= 0",
        )
        batch_op.create_check_constraint(
            "ck_agent_runs_items_succeeded_non_negative",
            "items_succeeded >= 0",
        )
        batch_op.create_check_constraint(
            "ck_agent_runs_items_failed_non_negative",
            "items_failed >= 0",
        )

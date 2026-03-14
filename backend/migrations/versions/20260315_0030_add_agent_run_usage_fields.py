"""add agent run usage fields

Revision ID: 20260315_0030
Revises: 20260314_0029
Create Date: 2026-03-15 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260315_0030"
down_revision: str | None = "20260314_0029"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("agent_runs")}

    if "provider_name" not in existing_columns:
        op.add_column("agent_runs", sa.Column("provider_name", sa.String(length=128), nullable=True))
    if "model_name" not in existing_columns:
        op.add_column("agent_runs", sa.Column("model_name", sa.String(length=256), nullable=True))
    if "input_tokens" not in existing_columns:
        op.add_column("agent_runs", sa.Column("input_tokens", sa.Integer(), nullable=True))
    if "output_tokens" not in existing_columns:
        op.add_column("agent_runs", sa.Column("output_tokens", sa.Integer(), nullable=True))
    if "total_tokens" not in existing_columns:
        op.add_column("agent_runs", sa.Column("total_tokens", sa.Integer(), nullable=True))

    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.create_check_constraint(
            "ck_agent_runs_input_tokens_non_negative",
            "input_tokens IS NULL OR input_tokens >= 0",
        )
        batch_op.create_check_constraint(
            "ck_agent_runs_output_tokens_non_negative",
            "output_tokens IS NULL OR output_tokens >= 0",
        )
        batch_op.create_check_constraint(
            "ck_agent_runs_total_tokens_non_negative",
            "total_tokens IS NULL OR total_tokens >= 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_constraint("ck_agent_runs_total_tokens_non_negative", type_="check")
        batch_op.drop_constraint("ck_agent_runs_output_tokens_non_negative", type_="check")
        batch_op.drop_constraint("ck_agent_runs_input_tokens_non_negative", type_="check")

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("agent_runs")}

    if "total_tokens" in existing_columns:
        op.drop_column("agent_runs", "total_tokens")
    if "output_tokens" in existing_columns:
        op.drop_column("agent_runs", "output_tokens")
    if "input_tokens" in existing_columns:
        op.drop_column("agent_runs", "input_tokens")
    if "model_name" in existing_columns:
        op.drop_column("agent_runs", "model_name")
    if "provider_name" in existing_columns:
        op.drop_column("agent_runs", "provider_name")

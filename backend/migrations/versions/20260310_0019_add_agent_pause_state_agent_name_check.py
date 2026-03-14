"""add agent_name check constraint to agent_pause_state

Revision ID: 20260310_0019
Revises: 20260310_0018
Create Date: 2026-03-11 00:00:00.000000

Add an agent_name validity check constraint to the agent_pause_state table
to match the data-integrity contract enforced on agent_runs and system_events.
Without this constraint, a stray row with an unknown agent_name would cause
fetchAgentPauseStates() to reject the entire response payload on the frontend.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260310_0019"
down_revision: str | None = "20260310_0018"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_VALID_AGENT_NAMES_SQL = (
    "'firehose', 'backfill', 'bouncer', 'analyst', 'overlord', 'combiner', 'obsession'"
)


def upgrade() -> None:
    with op.batch_alter_table("agent_pause_state") as batch_op:
        batch_op.create_check_constraint(
            "ck_agent_pause_state_agent_name_valid",
            f"agent_name IN ({_VALID_AGENT_NAMES_SQL})",
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_pause_state") as batch_op:
        batch_op.drop_constraint(
            "ck_agent_pause_state_agent_name_valid",
            type_="check",
        )

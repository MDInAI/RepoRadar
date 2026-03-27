"""add idea_scout to agent_name check constraints

Revision ID: 20260326_0039
Revises: 20260324_0038
Create Date: 2026-03-26 00:00:00.000000

Add 'idea_scout' to the agent_name allowlist CHECK constraints on
agent_runs, system_events, and agent_pause_state.  Without this,
start_agent_run() raises IntegrityError whenever IdeaScout tries to
record a run, making the worker-activity monitoring panel blind to all
IdeaScout cycles.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260326_0039"
down_revision: str | None = "20260324_0038"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_OLD_VALID = "'firehose', 'backfill', 'bouncer', 'analyst', 'overlord', 'combiner', 'obsession'"
_NEW_VALID = "'firehose', 'backfill', 'bouncer', 'analyst', 'overlord', 'combiner', 'obsession', 'idea_scout'"


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_constraint("ck_agent_runs_agent_name_valid", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_runs_agent_name_valid",
            f"agent_name IN ({_NEW_VALID})",
        )

    with op.batch_alter_table("system_events") as batch_op:
        batch_op.drop_constraint("ck_system_events_agent_name_valid", type_="check")
        batch_op.create_check_constraint(
            "ck_system_events_agent_name_valid",
            f"agent_name IN ({_NEW_VALID})",
        )

    with op.batch_alter_table("agent_pause_state") as batch_op:
        batch_op.drop_constraint("ck_agent_pause_state_agent_name_valid", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_pause_state_agent_name_valid",
            f"agent_name IN ({_NEW_VALID})",
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_constraint("ck_agent_runs_agent_name_valid", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_runs_agent_name_valid",
            f"agent_name IN ({_OLD_VALID})",
        )

    with op.batch_alter_table("system_events") as batch_op:
        batch_op.drop_constraint("ck_system_events_agent_name_valid", type_="check")
        batch_op.create_check_constraint(
            "ck_system_events_agent_name_valid",
            f"agent_name IN ({_OLD_VALID})",
        )

    with op.batch_alter_table("agent_pause_state") as batch_op:
        batch_op.drop_constraint("ck_agent_pause_state_agent_name_valid", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_pause_state_agent_name_valid",
            f"agent_name IN ({_OLD_VALID})",
        )

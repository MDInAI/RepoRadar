"""add agent_pause_state table

Revision ID: 20260310_0017
Revises: 20260310_0016
Create Date: 2026-03-10 18:30:00.000000

Add agent_pause_state table to track pause state for each agent, preventing
unsafe processing when critical failures occur.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260310_0017"
down_revision: str | None = "20260310_0016"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_pause_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("is_paused", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("paused_at", sa.DateTime(), nullable=True),
        sa.Column("pause_reason", sa.Text(), nullable=True),
        sa.Column("resume_condition", sa.Text(), nullable=True),
        sa.Column("triggered_by_event_id", sa.Integer(), nullable=True),
        sa.Column("resumed_at", sa.DateTime(), nullable=True),
        sa.Column("resumed_by", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(
            ["triggered_by_event_id"],
            ["system_events.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_name"),
    )
    op.create_index("ix_agent_pause_state_agent_name", "agent_pause_state", ["agent_name"])


def downgrade() -> None:
    op.drop_index("ix_agent_pause_state_agent_name", "agent_pause_state")
    op.drop_table("agent_pause_state")

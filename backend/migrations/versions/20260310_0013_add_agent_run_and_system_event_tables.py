"""add agent run and system event tables

Revision ID: 20260310_0013
Revises: 20260309_0012
Create Date: 2026-03-10 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260310_0013"
down_revision: str | None = "20260309_0012"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "completed",
                "failed",
                "skipped",
                name="agent_run_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("items_processed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_succeeded", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("error_context", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "agent_name IN ('firehose', 'backfill', 'bouncer', 'analyst', 'overlord', 'combiner', 'obsession')",
            name="ck_agent_runs_agent_name_valid",
        ),
        sa.CheckConstraint(
            "items_processed >= 0",
            name="ck_agent_runs_items_processed_non_negative",
        ),
        sa.CheckConstraint(
            "items_succeeded >= 0",
            name="ck_agent_runs_items_succeeded_non_negative",
        ),
        sa.CheckConstraint(
            "items_failed >= 0",
            name="ck_agent_runs_items_failed_non_negative",
        ),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_agent_runs_duration_non_negative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_agent_name", "agent_runs", ["agent_name"], unique=False)
    op.create_index("ix_agent_runs_started_at", "agent_runs", ["started_at"], unique=False)
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"], unique=False)

    op.create_table(
        "system_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                "info",
                "warning",
                "error",
                "critical",
                name="event_severity",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default=sa.text("'info'"),
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=True),
        sa.Column("agent_run_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
        sa.CheckConstraint(
            "agent_name IN ('firehose', 'backfill', 'bouncer', 'analyst', 'overlord', 'combiner', 'obsession')",
            name="ck_system_events_agent_name_valid",
        ),
        sa.CheckConstraint("event_type != ''", name="ck_system_events_event_type_not_blank"),
        sa.CheckConstraint("message != ''", name="ck_system_events_message_not_blank"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_events_agent_name", "system_events", ["agent_name"], unique=False)
    op.create_index(
        "ix_system_events_agent_run_id", "system_events", ["agent_run_id"], unique=False
    )
    op.create_index("ix_system_events_created_at", "system_events", ["created_at"], unique=False)
    op.create_index("ix_system_events_event_type", "system_events", ["event_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_system_events_event_type", table_name="system_events")
    op.drop_index("ix_system_events_created_at", table_name="system_events")
    op.drop_index("ix_system_events_agent_run_id", table_name="system_events")
    op.drop_index("ix_system_events_agent_name", table_name="system_events")
    op.drop_table("system_events")

    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_agent_runs_started_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_agent_name", table_name="agent_runs")
    op.drop_table("agent_runs")

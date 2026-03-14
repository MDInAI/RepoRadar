"""add failure classification fields to system_events

Revision ID: 20260310_0015
Revises: 20260310_0014
Create Date: 2026-03-10 13:00:00.000000

Add failure-detection columns to system_events so that detected API failures
and rate-limit conditions can be stored with structured context (classification,
severity, HTTP status, retry timing, affected repository, and upstream provider).
These columns are all nullable — existing events are unaffected.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260310_0015"
down_revision: str | None = "20260310_0014"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("system_events") as batch_op:
        batch_op.add_column(
            sa.Column(
                "failure_classification",
                sa.String(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "failure_severity",
                sa.String(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("http_status_code", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("retry_after_seconds", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("affected_repository_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("upstream_provider", sa.String(64), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_system_events_affected_repository_id_repository_intake",
            "repository_intake",
            ["affected_repository_id"],
            ["github_repository_id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_system_events_failure_classification",
            ["failure_classification"],
        )


def downgrade() -> None:
    with op.batch_alter_table("system_events") as batch_op:
        batch_op.drop_index("ix_system_events_failure_classification")
        batch_op.drop_constraint(
            "fk_system_events_affected_repository_id_repository_intake",
            type_="foreignkey",
        )
        batch_op.drop_column("upstream_provider")
        batch_op.drop_column("affected_repository_id")
        batch_op.drop_column("retry_after_seconds")
        batch_op.drop_column("http_status_code")
        batch_op.drop_column("failure_severity")
        batch_op.drop_column("failure_classification")

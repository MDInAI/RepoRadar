"""add upstream_provider constraint and failure_severity index

Revision ID: 20260310_0016
Revises: 20260310_0015
Create Date: 2026-03-10 17:45:00.000000

Add check constraints to upstream_provider, failure_classification, and failure_severity
columns to enforce valid enum values, and add index on failure_severity column for query performance.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260310_0016"
down_revision: str | None = "20260310_0015"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("system_events") as batch_op:
        batch_op.create_check_constraint(
            "ck_system_events_upstream_provider_valid",
            "upstream_provider IS NULL OR upstream_provider IN ('github', 'llm')",
        )
        batch_op.create_check_constraint(
            "ck_system_events_failure_classification_valid",
            "failure_classification IS NULL OR failure_classification IN ('retryable', 'blocking', 'rate_limited')",
        )
        batch_op.create_check_constraint(
            "ck_system_events_failure_severity_valid",
            "failure_severity IS NULL OR failure_severity IN ('warning', 'error', 'critical')",
        )
        batch_op.create_index(
            "ix_system_events_failure_severity",
            ["failure_severity"],
        )


def downgrade() -> None:
    with op.batch_alter_table("system_events") as batch_op:
        batch_op.drop_index("ix_system_events_failure_severity")
        batch_op.drop_constraint(
            "ck_system_events_failure_severity_valid",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_system_events_failure_classification_valid",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_system_events_upstream_provider_valid",
            type_="check",
        )

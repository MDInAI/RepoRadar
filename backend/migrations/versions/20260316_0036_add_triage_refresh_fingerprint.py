"""add triage refresh fingerprint fields

Revision ID: 20260316_0036
Revises: 20260316_0035
Create Date: 2026-03-16 18:15:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260316_0036"
down_revision: str | None = "20260316_0035"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("repository_triage_explanation")
    }

    if "triage_logic_version" not in existing_columns:
        op.add_column(
            "repository_triage_explanation",
            sa.Column("triage_logic_version", sa.String(length=64), nullable=True),
        )
    if "triage_config_fingerprint" not in existing_columns:
        op.add_column(
            "repository_triage_explanation",
            sa.Column("triage_config_fingerprint", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("repository_triage_explanation")
    }

    if "triage_config_fingerprint" in existing_columns:
        op.drop_column("repository_triage_explanation", "triage_config_fingerprint")
    if "triage_logic_version" in existing_columns:
        op.drop_column("repository_triage_explanation", "triage_logic_version")

"""create repository intake schema

Revision ID: 20260307_0001
Revises:
Create Date: 2026-03-07 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260307_0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

repository_discovery_source = sa.Enum(
    "unknown",
    "firehose",
    "backfill",
    name="repository_discovery_source",
    native_enum=False,
    create_constraint=True,
)
repository_queue_status = sa.Enum(
    "pending",
    "in_progress",
    "completed",
    "failed",
    name="repository_queue_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "repository_intake",
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "source_provider",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'github'"),
        ),
        sa.Column("owner_login", sa.String(length=255), nullable=False),
        sa.Column("repository_name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=511), nullable=False),
        sa.CheckConstraint("source_provider IN ('github')", name="ck_repository_intake_source_provider_valid"),
        sa.CheckConstraint("owner_login != ''", name="ck_repository_intake_owner_login_not_blank"),
        sa.CheckConstraint("repository_name != ''", name="ck_repository_intake_repository_name_not_blank"),
        sa.CheckConstraint("full_name != ''", name="ck_repository_intake_full_name_not_blank"),
        sa.CheckConstraint(
            "full_name = owner_login || '/' || repository_name",
            name="ck_repository_intake_full_name_consistent",
        ),
        sa.Column(
            "discovery_source",
            repository_discovery_source,
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column(
            "queue_status",
            repository_queue_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
        sa.Column(
            "queue_created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
        sa.Column(
            "status_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint(
            "github_repository_id",
            name="pk_repository_intake",
        ),
    )
    op.create_index(
        "ix_repository_intake_discovery_source",
        "repository_intake",
        ["discovery_source"],
        unique=False,
    )
    op.create_index(
        "ix_repository_intake_full_name",
        "repository_intake",
        ["full_name"],
        unique=False,
    )
    op.create_index(
        "ix_repository_intake_queue_status",
        "repository_intake",
        ["queue_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_repository_intake_queue_status", table_name="repository_intake")
    op.drop_index("ix_repository_intake_full_name", table_name="repository_intake")
    op.drop_index("ix_repository_intake_discovery_source", table_name="repository_intake")
    op.drop_table("repository_intake")

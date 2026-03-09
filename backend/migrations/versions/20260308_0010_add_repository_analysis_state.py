"""add repository analysis state

Revision ID: 20260308_0010
Revises: 20260308_0009
Create Date: 2026-03-08 23:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260308_0010"
down_revision: str | None = "20260308_0009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

repository_analysis_status = sa.Enum(
    "pending",
    "in_progress",
    "completed",
    "failed",
    name="repository_analysis_status",
    native_enum=False,
    create_constraint=True,
)

repository_analysis_failure_code = sa.Enum(
    "transport_error",
    "rate_limited",
    "missing_readme",
    "invalid_readme_payload",
    "invalid_analysis_output",
    "persistence_error",
    name="repository_analysis_failure_code",
    native_enum=False,
    create_constraint=True,
)

repository_monetization_potential = sa.Enum(
    "low",
    "medium",
    "high",
    name="repository_monetization_potential",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    with op.batch_alter_table("repository_intake") as batch_op:
        batch_op.add_column(
            sa.Column(
                "analysis_status",
                repository_analysis_status,
                nullable=False,
                server_default=sa.text("'pending'"),
            )
        )
        batch_op.add_column(
            sa.Column("analysis_started_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("analysis_completed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("analysis_last_attempted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("analysis_last_failed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "analysis_failure_code",
                repository_analysis_failure_code,
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("analysis_failure_message", sa.Text(), nullable=True))
        batch_op.create_index(
            "ix_repository_intake_analysis_status",
            ["analysis_status"],
            unique=False,
        )

    op.create_table(
        "repository_analysis_result",
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "source_provider",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'github'"),
        ),
        sa.Column(
            "source_kind",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'repository_readme'"),
        ),
        sa.Column(
            "source_metadata",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "monetization_potential",
            repository_monetization_potential,
            nullable=False,
        ),
        sa.Column(
            "pros",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "cons",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "missing_feature_signals",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_provider IN ('github')",
            name="ck_repository_analysis_result_source_provider_valid",
        ),
        sa.CheckConstraint(
            "source_kind != ''",
            name="ck_repository_analysis_result_source_kind_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["github_repository_id"],
            ["repository_intake.github_repository_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("github_repository_id"),
    )


def downgrade() -> None:
    op.drop_table("repository_analysis_result")

    with op.batch_alter_table("repository_intake") as batch_op:
        batch_op.drop_index("ix_repository_intake_analysis_status")
        batch_op.drop_column("analysis_failure_message")
        batch_op.drop_column("analysis_failure_code")
        batch_op.drop_column("analysis_last_failed_at")
        batch_op.drop_column("analysis_last_attempted_at")
        batch_op.drop_column("analysis_completed_at")
        batch_op.drop_column("analysis_started_at")
        batch_op.drop_column("analysis_status")

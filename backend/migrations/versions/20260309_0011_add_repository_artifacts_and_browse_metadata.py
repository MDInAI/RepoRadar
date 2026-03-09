"""add repository artifacts and browse metadata

Revision ID: 20260309_0011
Revises: 20260308_0010
Create Date: 2026-03-09 10:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260309_0011"
down_revision: str | None = "20260308_0010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

repository_artifact_kind = sa.Enum(
    "readme_snapshot",
    "analysis_result",
    name="repository_artifact_kind",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    with op.batch_alter_table("repository_intake") as batch_op:
        batch_op.add_column(
            sa.Column(
                "stargazers_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "forks_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_check_constraint(
            "ck_repository_intake_stars_non_negative",
            "stargazers_count >= 0",
        )
        batch_op.create_check_constraint(
            "ck_repository_intake_forks_non_negative",
            "forks_count >= 0",
        )
        batch_op.create_index("ix_repository_intake_pushed_at", ["pushed_at"], unique=False)

    op.create_table(
        "repository_artifact",
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column("artifact_kind", repository_artifact_kind, nullable=False),
        sa.Column("runtime_relative_path", sa.String(length=1024), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column(
            "content_type",
            sa.String(length=255),
            nullable=False,
            server_default=sa.text("'application/octet-stream'"),
        ),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column(
            "provenance_metadata",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "runtime_relative_path != ''",
            name="ck_repository_artifact_path_not_blank",
        ),
        sa.CheckConstraint(
            "source_kind != ''",
            name="ck_repository_artifact_source_kind_not_blank",
        ),
        sa.CheckConstraint(
            "content_sha256 != ''",
            name="ck_repository_artifact_sha_not_blank",
        ),
        sa.CheckConstraint(
            "content_type != ''",
            name="ck_repository_artifact_content_type_not_blank",
        ),
        sa.CheckConstraint(
            "byte_size >= 0",
            name="ck_repository_artifact_byte_size_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["github_repository_id"],
            ["repository_intake.github_repository_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("github_repository_id", "artifact_kind"),
    )
    op.create_index(
        "ix_repository_artifact_generated_at",
        "repository_artifact",
        ["generated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_repository_artifact_generated_at", table_name="repository_artifact")
    op.drop_table("repository_artifact")

    with op.batch_alter_table("repository_intake") as batch_op:
        batch_op.drop_index("ix_repository_intake_pushed_at")
        batch_op.drop_constraint("ck_repository_intake_forks_non_negative", type_="check")
        batch_op.drop_constraint("ck_repository_intake_stars_non_negative", type_="check")
        batch_op.drop_column("pushed_at")
        batch_op.drop_column("forks_count")
        batch_op.drop_column("stargazers_count")

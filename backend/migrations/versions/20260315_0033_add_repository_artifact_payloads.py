"""add repository artifact payloads

Revision ID: 20260315_0033
Revises: 20260315_0032
Create Date: 2026-03-15 18:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260315_0033"
down_revision = "20260315_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repository_artifact_payload",
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column("artifact_kind", sa.String(length=32), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column(
            "content_encoding",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'utf-8'"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "content_encoding != ''",
            name="ck_repository_artifact_payload_encoding_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["github_repository_id"],
            ["repository_intake.github_repository_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["github_repository_id", "artifact_kind"],
            ["repository_artifact.github_repository_id", "repository_artifact.artifact_kind"],
            name="fk_repository_artifact_payload_artifact",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "github_repository_id",
            "artifact_kind",
        ),
    )
    op.create_index(
        "ix_repository_artifact_payload_updated_at",
        "repository_artifact_payload",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_repository_artifact_payload_updated_at", table_name="repository_artifact_payload")
    op.drop_table("repository_artifact_payload")

"""add repository user curation

Revision ID: 20260309_0012
Revises: 20260309_0011
Create Date: 2026-03-09 18:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260309_0012"
down_revision: str | None = "20260309_0011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repository_user_curation",
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "is_starred",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("starred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
        sa.ForeignKeyConstraint(
            ["github_repository_id"],
            ["repository_intake.github_repository_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("github_repository_id"),
    )
    op.create_index(
        "ix_repository_user_curation_is_starred",
        "repository_user_curation",
        ["is_starred"],
        unique=False,
    )

    op.create_table(
        "repository_user_tag",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_label", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
        sa.CheckConstraint(
            "tag_label != ''",
            name="ck_repository_user_tag_label_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["github_repository_id"],
            ["repository_intake.github_repository_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "github_repository_id",
            "tag_label",
            name="uq_repository_user_tag_github_repository_id_tag_label",
        ),
    )
    op.create_index(
        "ix_repository_user_tag_github_repository_id",
        "repository_user_tag",
        ["github_repository_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_repository_user_tag_github_repository_id",
        table_name="repository_user_tag",
    )
    op.drop_table("repository_user_tag")

    op.drop_index(
        "ix_repository_user_curation_is_starred",
        table_name="repository_user_curation",
    )
    op.drop_table("repository_user_curation")

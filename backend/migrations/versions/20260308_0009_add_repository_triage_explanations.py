"""add repository triage explanations

Revision ID: 20260308_0009
Revises: 20260308_0008
Create Date: 2026-03-08 22:15:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260308_0009"
down_revision: str | None = "20260308_0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

repository_triage_explanation_kind = sa.Enum(
    "exclude_rule",
    "include_rule",
    "allowlist_miss",
    "pass_through",
    name="repository_triage_explanation_kind",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "repository_triage_explanation",
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "explanation_kind",
            repository_triage_explanation_kind,
            nullable=False,
        ),
        sa.Column("explanation_summary", sa.Text(), nullable=False),
        sa.Column(
            "matched_include_rules",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "matched_exclude_rules",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("explained_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "explanation_summary != ''",
            name="ck_repository_triage_explanation_summary_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["github_repository_id"],
            ["repository_intake.github_repository_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("github_repository_id"),
    )


def downgrade() -> None:
    op.drop_table("repository_triage_explanation")

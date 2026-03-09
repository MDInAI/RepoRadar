"""add repository triage state

Revision ID: 20260308_0008
Revises: 20260308_0007
Create Date: 2026-03-08 21:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260308_0008"
down_revision: str | None = "20260308_0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

repository_triage_status = sa.Enum(
    "pending",
    "accepted",
    "rejected",
    name="repository_triage_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    with op.batch_alter_table("repository_intake") as batch_op:
        batch_op.add_column(sa.Column("repository_description", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "triage_status",
                repository_triage_status,
                nullable=False,
                server_default=sa.text("'pending'"),
            )
        )
        batch_op.add_column(sa.Column("triaged_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(
            "ix_repository_intake_triage_status",
            ["triage_status"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("repository_intake") as batch_op:
        batch_op.drop_index("ix_repository_intake_triage_status")
        batch_op.drop_column("triaged_at")
        batch_op.drop_column("triage_status")
        batch_op.drop_column("repository_description")

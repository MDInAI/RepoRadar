"""add firehose mode metadata to repository intake

Revision ID: 20260307_0002
Revises: 20260307_0001
Create Date: 2026-03-07 13:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260307_0002"
down_revision: str | None = "20260307_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

repository_firehose_mode = sa.Enum(
    "new",
    "trending",
    name="repository_firehose_mode",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    with op.batch_alter_table("repository_intake") as batch_op:
        batch_op.add_column(
            sa.Column(
                "firehose_discovery_mode",
                repository_firehose_mode,
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "ck_repository_intake_firehose_mode_matches_discovery_source",
            (
                "("
                "discovery_source = 'firehose' AND firehose_discovery_mode IS NOT NULL"
                ") OR ("
                "discovery_source != 'firehose' AND firehose_discovery_mode IS NULL"
                ")"
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("repository_intake") as batch_op:
        batch_op.drop_constraint(
            "ck_repository_intake_firehose_mode_matches_discovery_source",
            type_="check",
        )
        batch_op.drop_column("firehose_discovery_mode")

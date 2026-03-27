"""allow idea_scout as a repository intake discovery source

Revision ID: 20260324_0038
Revises: 20260324_0037
Create Date: 2026-03-24 20:45:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260324_0038"
down_revision: str | None = "20260324_0037"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_OLD_DISCOVERY_SOURCE_ENUM = sa.Enum(
    "unknown",
    "firehose",
    "backfill",
    name="repository_discovery_source",
    native_enum=False,
    create_constraint=True,
)

_NEW_DISCOVERY_SOURCE_ENUM = sa.Enum(
    "unknown",
    "firehose",
    "backfill",
    "idea_scout",
    name="repository_discovery_source",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    with op.batch_alter_table("repository_intake", recreate="always") as batch_op:
        batch_op.alter_column(
            "discovery_source",
            existing_type=_OLD_DISCOVERY_SOURCE_ENUM,
            type_=_NEW_DISCOVERY_SOURCE_ENUM,
            existing_nullable=False,
            existing_server_default=sa.text("'unknown'"),
        )


def downgrade() -> None:
    with op.batch_alter_table("repository_intake", recreate="always") as batch_op:
        batch_op.alter_column(
            "discovery_source",
            existing_type=_NEW_DISCOVERY_SOURCE_ENUM,
            type_=_OLD_DISCOVERY_SOURCE_ENUM,
            existing_nullable=False,
            existing_server_default=sa.text("'unknown'"),
        )

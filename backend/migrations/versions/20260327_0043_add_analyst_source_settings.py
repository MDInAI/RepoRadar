"""add analyst_source_settings table

Revision ID: 20260327_0043
Revises: 20260327_0042
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa

revision = "20260327_0043"
down_revision = "20260327_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analyst_source_settings",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("firehose_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("backfill_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    # Insert the singleton row with defaults (firehose off, backfill off)
    op.execute("INSERT INTO analyst_source_settings (id, firehose_enabled, backfill_enabled) VALUES (1, 0, 0)")


def downgrade() -> None:
    op.drop_table("analyst_source_settings")

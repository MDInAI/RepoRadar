"""add synthesis run obsession fk

Revision ID: 20260313_0026
Revises: 20260313_0025
Create Date: 2026-03-13 23:14:23.340000

"""
from alembic import op
import sqlalchemy as sa


revision = '20260313_0026'
down_revision = '20260313_0025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_columns = {column["name"] for column in inspector.get_columns("synthesis_run")}
    if "obsession_context_id" not in existing_columns:
        op.add_column("synthesis_run", sa.Column("obsession_context_id", sa.Integer(), nullable=True))

    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes("synthesis_run")}
    if "ix_synthesis_run_obsession_context_id" not in existing_indexes:
        op.create_index("ix_synthesis_run_obsession_context_id", "synthesis_run", ["obsession_context_id"])

    if bind.dialect.name != "sqlite":
        existing_foreign_keys = {
            foreign_key["name"]
            for foreign_key in inspector.get_foreign_keys("synthesis_run")
            if foreign_key.get("name")
        }
        if "fk_synthesis_run_obsession_context_id" not in existing_foreign_keys:
            op.create_foreign_key(
                "fk_synthesis_run_obsession_context_id",
                "synthesis_run",
                "obsession_context",
                ["obsession_context_id"],
                ["id"],
                ondelete="CASCADE",
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_indexes = {index["name"] for index in inspector.get_indexes("synthesis_run")}
    if "ix_synthesis_run_obsession_context_id" in existing_indexes:
        op.drop_index("ix_synthesis_run_obsession_context_id", table_name="synthesis_run")

    if bind.dialect.name != "sqlite":
        existing_foreign_keys = {
            foreign_key["name"]
            for foreign_key in inspector.get_foreign_keys("synthesis_run")
            if foreign_key.get("name")
        }
        if "fk_synthesis_run_obsession_context_id" in existing_foreign_keys:
            op.drop_constraint("fk_synthesis_run_obsession_context_id", "synthesis_run", type_="foreignkey")

    existing_columns = {column["name"] for column in inspector.get_columns("synthesis_run")}
    if "obsession_context_id" in existing_columns:
        op.drop_column("synthesis_run", "obsession_context_id")

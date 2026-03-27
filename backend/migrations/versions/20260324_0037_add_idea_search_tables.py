"""add idea_search tables and extend obsession_context

Revision ID: 20260324_0037
Revises: 20260316_0036
Create Date: 2026-03-24 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260324_0037"
down_revision: str | None = "20260316_0036"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_OBSESSION_TARGET_CHECK_NAME = "ck_obsession_context_exactly_one_target"
_OBSESSION_IDEA_SEARCH_FK_NAME = "fk_obsession_context_idea_search_id"
_NEW_OBSESSION_TARGET_CHECK_SQL = (
    "("
    "  (idea_family_id IS NOT NULL AND synthesis_run_id IS NULL AND idea_search_id IS NULL)"
    "  OR (idea_family_id IS NULL AND synthesis_run_id IS NOT NULL AND idea_search_id IS NULL)"
    "  OR (idea_family_id IS NULL AND synthesis_run_id IS NULL AND idea_search_id IS NOT NULL)"
    ")"
)
_OLD_OBSESSION_TARGET_CHECK_SQL = (
    "(idea_family_id IS NOT NULL AND synthesis_run_id IS NULL) OR "
    "(idea_family_id IS NULL AND synthesis_run_id IS NOT NULL)"
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_names() -> set[str]:
    return set(_inspector().get_table_names())


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {index["name"] for index in _inspector().get_indexes(table_name)}


def _check_constraints(table_name: str) -> dict[str, str]:
    constraints: dict[str, str] = {}
    for constraint in _inspector().get_check_constraints(table_name):
        name = constraint.get("name")
        if name:
            constraints[name] = constraint.get("sqltext") or ""
    return constraints


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split())


def _ensure_index(index_name: str, table_name: str, columns: list[str]) -> None:
    if index_name not in _index_names(table_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    # --- idea_search ---
    if "idea_search" not in _table_names():
        op.create_table(
            "idea_search",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True, nullable=False),
            sa.Column("idea_text", sa.Text, nullable=False),
            sa.Column("search_queries", sa.Text, nullable=False, server_default="[]"),
            sa.Column(
                "direction",
                sa.String(16),
                nullable=False,
            ),
            sa.Column(
                "status",
                sa.String(16),
                nullable=False,
                server_default="active",
            ),
            sa.Column(
                "obsession_context_id",
                sa.Integer,
                sa.ForeignKey("obsession_context.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("total_repos_found", sa.Integer, nullable=False, server_default="0"),
            sa.Column(
                "created_at",
                sa.DateTime,
                nullable=False,
                server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime,
                nullable=False,
                server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
            ),
            sa.CheckConstraint("idea_text != ''", name="ck_idea_search_idea_text_not_blank"),
            sa.CheckConstraint("total_repos_found >= 0", name="ck_idea_search_total_repos_non_negative"),
            sa.CheckConstraint(
                "direction IN ('backward', 'forward')",
                name="ck_idea_search_direction_valid",
            ),
            sa.CheckConstraint(
                "status IN ('active', 'paused', 'completed', 'cancelled')",
                name="ck_idea_search_status_valid",
            ),
        )
    _ensure_index("ix_idea_search_status", "idea_search", ["status"])
    _ensure_index("ix_idea_search_direction", "idea_search", ["direction"])
    _ensure_index("ix_idea_search_obsession_context_id", "idea_search", ["obsession_context_id"])

    # --- idea_search_progress ---
    if "idea_search_progress" not in _table_names():
        op.create_table(
            "idea_search_progress",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True, nullable=False),
            sa.Column(
                "idea_search_id",
                sa.Integer,
                sa.ForeignKey("idea_search.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("query_index", sa.Integer, nullable=False, server_default="0"),
            sa.Column("window_start_date", sa.Date, nullable=False),
            sa.Column("created_before_boundary", sa.Date, nullable=False),
            sa.Column("created_before_cursor", sa.DateTime, nullable=True),
            sa.Column("next_page", sa.Integer, nullable=False, server_default="1"),
            sa.Column("pages_processed_in_run", sa.Integer, nullable=False, server_default="0"),
            sa.Column("exhausted", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("resume_required", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("last_checkpointed_at", sa.DateTime, nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime,
                nullable=False,
                server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
            ),
            sa.CheckConstraint("next_page > 0", name="ck_idea_search_progress_next_page_positive"),
            sa.CheckConstraint(
                "window_start_date < created_before_boundary",
                name="ck_idea_search_progress_window_before_boundary",
            ),
            sa.UniqueConstraint(
                "idea_search_id",
                "query_index",
                name="uq_idea_search_progress_search_query",
            ),
        )
    _ensure_index("ix_idea_search_progress_idea_search_id", "idea_search_progress", ["idea_search_id"])

    # --- idea_search_discovery ---
    if "idea_search_discovery" not in _table_names():
        op.create_table(
            "idea_search_discovery",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True, nullable=False),
            sa.Column(
                "idea_search_id",
                sa.Integer,
                sa.ForeignKey("idea_search.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "github_repository_id",
                sa.BigInteger,
                sa.ForeignKey("repository_intake.github_repository_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "discovered_at",
                sa.DateTime,
                nullable=False,
                server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
            ),
            sa.UniqueConstraint(
                "idea_search_id",
                "github_repository_id",
                name="uq_idea_search_discovery_search_repo",
            ),
        )
    _ensure_index("ix_idea_search_discovery_idea_search_id", "idea_search_discovery", ["idea_search_id"])
    _ensure_index(
        "ix_idea_search_discovery_github_repository_id",
        "idea_search_discovery",
        ["github_repository_id"],
    )

    # --- Extend obsession_context with idea_search_id and idea_text ---
    # SQLite doesn't support ALTER CONSTRAINT, so we use batch mode to
    # add columns and replace the check constraint.
    obsession_columns = _column_names("obsession_context")
    obsession_checks = _check_constraints("obsession_context")
    existing_target_check = obsession_checks.get(_OBSESSION_TARGET_CHECK_NAME)
    needs_target_check_update = _normalize_sql(existing_target_check or "") != _normalize_sql(
        _NEW_OBSESSION_TARGET_CHECK_SQL
    )

    if (
        "idea_search_id" not in obsession_columns
        or "idea_text" not in obsession_columns
        or needs_target_check_update
    ):
        with op.batch_alter_table("obsession_context") as batch_op:
            if "idea_search_id" not in obsession_columns:
                batch_op.add_column(
                    sa.Column(
                        "idea_search_id",
                        sa.Integer,
                        nullable=True,
                    ),
                )
                batch_op.create_foreign_key(
                    _OBSESSION_IDEA_SEARCH_FK_NAME,
                    "idea_search",
                    ["idea_search_id"],
                    ["id"],
                    ondelete="CASCADE",
                )
            if "idea_text" not in obsession_columns:
                batch_op.add_column(
                    sa.Column("idea_text", sa.Text, nullable=True),
                )
            if existing_target_check and needs_target_check_update:
                batch_op.drop_constraint(_OBSESSION_TARGET_CHECK_NAME, type_="check")
            if needs_target_check_update:
                batch_op.create_check_constraint(
                    _OBSESSION_TARGET_CHECK_NAME,
                    _NEW_OBSESSION_TARGET_CHECK_SQL,
                )

    _ensure_index("ix_obsession_context_idea_search_id", "obsession_context", ["idea_search_id"])


def downgrade() -> None:
    if "obsession_context" in _table_names():
        obsession_columns = _column_names("obsession_context")
        obsession_indexes = _index_names("obsession_context")
        obsession_checks = _check_constraints("obsession_context")
        existing_target_check = obsession_checks.get(_OBSESSION_TARGET_CHECK_NAME)
        needs_target_check_update = _normalize_sql(existing_target_check or "") != _normalize_sql(
            _OLD_OBSESSION_TARGET_CHECK_SQL
        )

        if (
            "idea_search_id" in obsession_columns
            or "idea_text" in obsession_columns
            or needs_target_check_update
        ):
            with op.batch_alter_table("obsession_context") as batch_op:
                if "ix_obsession_context_idea_search_id" in obsession_indexes:
                    batch_op.drop_index("ix_obsession_context_idea_search_id")
                if "idea_search_id" in obsession_columns:
                    batch_op.drop_constraint(_OBSESSION_IDEA_SEARCH_FK_NAME, type_="foreignkey")
                if existing_target_check and needs_target_check_update:
                    batch_op.drop_constraint(_OBSESSION_TARGET_CHECK_NAME, type_="check")
                if "idea_text" in obsession_columns:
                    batch_op.drop_column("idea_text")
                if "idea_search_id" in obsession_columns:
                    batch_op.drop_column("idea_search_id")
                if needs_target_check_update:
                    batch_op.create_check_constraint(
                        _OBSESSION_TARGET_CHECK_NAME,
                        _OLD_OBSESSION_TARGET_CHECK_SQL,
                    )

    if "idea_search_discovery" in _table_names():
        op.drop_table("idea_search_discovery")
    if "idea_search_progress" in _table_names():
        op.drop_table("idea_search_progress")
    if "idea_search" in _table_names():
        op.drop_table("idea_search")

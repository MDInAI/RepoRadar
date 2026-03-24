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


def upgrade() -> None:
    # --- idea_search ---
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
    op.create_index("ix_idea_search_status", "idea_search", ["status"])
    op.create_index("ix_idea_search_direction", "idea_search", ["direction"])
    op.create_index("ix_idea_search_obsession_context_id", "idea_search", ["obsession_context_id"])

    # --- idea_search_progress ---
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
    op.create_index("ix_idea_search_progress_idea_search_id", "idea_search_progress", ["idea_search_id"])

    # --- idea_search_discovery ---
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
    op.create_index("ix_idea_search_discovery_idea_search_id", "idea_search_discovery", ["idea_search_id"])
    op.create_index(
        "ix_idea_search_discovery_github_repository_id",
        "idea_search_discovery",
        ["github_repository_id"],
    )

    # --- Extend obsession_context with idea_search_id and idea_text ---
    # SQLite doesn't support ALTER CONSTRAINT, so we use batch mode to
    # add columns and replace the check constraint.
    with op.batch_alter_table("obsession_context") as batch_op:
        batch_op.add_column(
            sa.Column(
                "idea_search_id",
                sa.Integer,
                sa.ForeignKey("idea_search.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        batch_op.add_column(
            sa.Column("idea_text", sa.Text, nullable=True),
        )
        batch_op.create_index("ix_obsession_context_idea_search_id", ["idea_search_id"])
        batch_op.drop_constraint("ck_obsession_context_exactly_one_target", type_="check")
        batch_op.create_check_constraint(
            "ck_obsession_context_exactly_one_target",
            "("
            "  (idea_family_id IS NOT NULL AND synthesis_run_id IS NULL AND idea_search_id IS NULL)"
            "  OR (idea_family_id IS NULL AND synthesis_run_id IS NOT NULL AND idea_search_id IS NULL)"
            "  OR (idea_family_id IS NULL AND synthesis_run_id IS NULL AND idea_search_id IS NOT NULL)"
            ")",
        )


def downgrade() -> None:
    with op.batch_alter_table("obsession_context") as batch_op:
        batch_op.drop_constraint("ck_obsession_context_exactly_one_target", type_="check")
        batch_op.drop_index("ix_obsession_context_idea_search_id")
        batch_op.drop_column("idea_text")
        batch_op.drop_column("idea_search_id")
        batch_op.create_check_constraint(
            "ck_obsession_context_exactly_one_target",
            "(idea_family_id IS NOT NULL AND synthesis_run_id IS NULL) OR "
            "(idea_family_id IS NULL AND synthesis_run_id IS NOT NULL)",
        )

    op.drop_table("idea_search_discovery")
    op.drop_table("idea_search_progress")
    op.drop_table("idea_search")

from __future__ import annotations

from datetime import timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session as SQLModelSession


def _build_alembic_config(database_url: str) -> Config:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_repository_intake_migration_creates_schema_and_enforces_identity(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "repository-schema.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)

    assert "repository_intake" in inspector.get_table_names()
    assert "backfill_progress" in inspector.get_table_names()
    assert "firehose_progress" in inspector.get_table_names()
    assert "repository_triage_explanation" in inspector.get_table_names()
    assert "repository_analysis_result" in inspector.get_table_names()
    assert "repository_artifact" in inspector.get_table_names()
    assert inspector.get_pk_constraint("repository_intake")["constrained_columns"] == [
        "github_repository_id"
    ]
    assert inspector.get_pk_constraint("backfill_progress")["constrained_columns"] == [
        "source_provider"
    ]
    assert inspector.get_pk_constraint("firehose_progress")["constrained_columns"] == [
        "source_provider"
    ]
    assert inspector.get_pk_constraint("repository_triage_explanation")[
        "constrained_columns"
    ] == ["github_repository_id"]

    columns = {column["name"]: column for column in inspector.get_columns("repository_intake")}
    assert {
        "github_repository_id",
        "source_provider",
        "owner_login",
        "repository_name",
        "full_name",
        "repository_description",
        "stargazers_count",
        "forks_count",
        "pushed_at",
        "discovery_source",
        "firehose_discovery_mode",
        "queue_status",
        "triage_status",
        "discovered_at",
        "queue_created_at",
        "status_updated_at",
        "processing_started_at",
        "processing_completed_at",
        "last_failed_at",
        "triaged_at",
        "analysis_status",
        "analysis_started_at",
        "analysis_completed_at",
        "analysis_last_attempted_at",
        "analysis_last_failed_at",
        "analysis_failure_code",
        "analysis_failure_message",
    } <= set(columns)

    assert not columns["github_repository_id"]["nullable"]
    assert not columns["queue_status"]["nullable"]
    assert not columns["status_updated_at"]["nullable"]

    assert {index["name"] for index in inspector.get_indexes("repository_intake")} == {
        "ix_repository_intake_discovery_source",
        "ix_repository_intake_full_name",
        "ix_repository_intake_analysis_status",
        "ix_repository_intake_pushed_at",
        "ix_repository_intake_queue_status",
        "ix_repository_intake_triage_status",
    }

    backfill_columns = {
        column["name"]: column for column in inspector.get_columns("backfill_progress")
    }
    assert {
        "source_provider",
        "window_start_date",
        "created_before_boundary",
        "created_before_cursor",
        "next_page",
        "pages_processed_in_run",
        "exhausted",
        "last_checkpointed_at",
        "updated_at",
    } <= set(backfill_columns)
    assert not backfill_columns["window_start_date"]["nullable"]
    assert not backfill_columns["created_before_boundary"]["nullable"]
    assert not backfill_columns["next_page"]["nullable"]

    firehose_columns = {
        column["name"]: column for column in inspector.get_columns("firehose_progress")
    }
    assert {
        "source_provider",
        "active_mode",
        "next_page",
        "pages_processed_in_run",
        "new_anchor_date",
        "trending_anchor_date",
        "run_started_at",
        "resume_required",
        "last_checkpointed_at",
        "updated_at",
    } <= set(firehose_columns)
    assert not firehose_columns["next_page"]["nullable"]
    assert not firehose_columns["resume_required"]["nullable"]

    explanation_columns = {
        column["name"]: column
        for column in inspector.get_columns("repository_triage_explanation")
    }
    assert {
        "github_repository_id",
        "explanation_kind",
        "explanation_summary",
        "matched_include_rules",
        "matched_exclude_rules",
        "explained_at",
    } <= set(explanation_columns)
    assert not explanation_columns["explanation_kind"]["nullable"]
    assert not explanation_columns["explanation_summary"]["nullable"]
    assert not explanation_columns["matched_include_rules"]["nullable"]
    assert not explanation_columns["matched_exclude_rules"]["nullable"]
    assert not explanation_columns["explained_at"]["nullable"]

    explanation_foreign_keys = inspector.get_foreign_keys("repository_triage_explanation")
    assert len(explanation_foreign_keys) == 1
    assert explanation_foreign_keys[0]["referred_table"] == "repository_intake"
    assert explanation_foreign_keys[0]["referred_columns"] == ["github_repository_id"]

    analysis_columns = {
        column["name"]: column for column in inspector.get_columns("repository_analysis_result")
    }
    assert {
        "github_repository_id",
        "source_provider",
        "source_kind",
        "source_metadata",
        "monetization_potential",
        "pros",
        "cons",
        "missing_feature_signals",
        "analyzed_at",
    } <= set(analysis_columns)
    assert not analysis_columns["source_provider"]["nullable"]
    assert not analysis_columns["source_kind"]["nullable"]
    assert not analysis_columns["source_metadata"]["nullable"]

    analysis_foreign_keys = inspector.get_foreign_keys("repository_analysis_result")
    assert len(analysis_foreign_keys) == 1
    assert analysis_foreign_keys[0]["referred_table"] == "repository_intake"
    assert analysis_foreign_keys[0]["referred_columns"] == ["github_repository_id"]

    artifact_columns = {
        column["name"]: column for column in inspector.get_columns("repository_artifact")
    }
    assert {
        "github_repository_id",
        "artifact_kind",
        "runtime_relative_path",
        "content_sha256",
        "byte_size",
        "content_type",
        "source_kind",
        "source_url",
        "provenance_metadata",
        "generated_at",
    } <= set(artifact_columns)
    assert not artifact_columns["artifact_kind"]["nullable"]
    assert not artifact_columns["runtime_relative_path"]["nullable"]
    assert not artifact_columns["content_sha256"]["nullable"]
    assert not artifact_columns["byte_size"]["nullable"]
    assert not artifact_columns["generated_at"]["nullable"]

    artifact_foreign_keys = inspector.get_foreign_keys("repository_artifact")
    assert len(artifact_foreign_keys) == 1
    assert artifact_foreign_keys[0]["referred_table"] == "repository_intake"
    assert artifact_foreign_keys[0]["referred_columns"] == ["github_repository_id"]

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO repository_intake (
                    github_repository_id,
                    owner_login,
                    repository_name,
                    full_name
                ) VALUES (
                    :github_repository_id,
                    :owner_login,
                    :repository_name,
                    :full_name
                )
                """
            ),
            {
                "github_repository_id": 987654321,
                "owner_login": "octocat",
                "repository_name": "hello-world",
                "full_name": "octocat/hello-world",
            },
        )

        row = connection.execute(
            text(
                """
                SELECT source_provider, discovery_source, firehose_discovery_mode, queue_status
                , repository_description, stargazers_count, forks_count, pushed_at
                , triage_status, triaged_at, analysis_status
                , analysis_started_at, analysis_failure_code
                FROM repository_intake
                WHERE github_repository_id = :github_repository_id
                """
            ),
            {"github_repository_id": 987654321},
        ).one()

        assert row.source_provider == "github"
        assert row.discovery_source == "unknown"
        assert row.firehose_discovery_mode is None
        assert row.queue_status == "pending"
        assert row.repository_description is None
        assert row.stargazers_count == 0
        assert row.forks_count == 0
        assert row.pushed_at is None
        assert row.triage_status == "pending"
        assert row.triaged_at is None
        assert row.analysis_status == "pending"
        assert row.analysis_started_at is None
        assert row.analysis_failure_code is None
        assert (
            connection.execute(text("SELECT COUNT(*) FROM repository_triage_explanation")).scalar_one()
            == 0
        )
        assert (
            connection.execute(text("SELECT COUNT(*) FROM repository_analysis_result")).scalar_one()
            == 0
        )

        connection.execute(
            text(
                """
                INSERT INTO repository_triage_explanation (
                    github_repository_id,
                    explanation_kind,
                    explanation_summary,
                    matched_include_rules,
                    matched_exclude_rules,
                    explained_at
                ) VALUES (
                    :github_repository_id,
                    :explanation_kind,
                    :explanation_summary,
                    :matched_include_rules,
                    :matched_exclude_rules,
                    :explained_at
                )
                """
            ),
            {
                "github_repository_id": 987654321,
                "explanation_kind": "include_rule",
                "explanation_summary": "Accepted because include rules matched: saas.",
                "matched_include_rules": '["saas"]',
                "matched_exclude_rules": "[]",
                "explained_at": "2026-03-08 12:30:00+00:00",
            },
        )

        explanation_row = connection.execute(
            text(
                """
                SELECT explanation_kind, explanation_summary, matched_include_rules,
                       matched_exclude_rules, explained_at
                FROM repository_triage_explanation
                WHERE github_repository_id = :github_repository_id
                """
            ),
            {"github_repository_id": 987654321},
        ).one()
        assert explanation_row.explanation_kind == "include_rule"
        assert explanation_row.explanation_summary == (
            "Accepted because include rules matched: saas."
        )
        assert explanation_row.matched_include_rules == '["saas"]'
        assert explanation_row.matched_exclude_rules == "[]"
        assert str(explanation_row.explained_at).startswith("2026-03-08 12:30:00")

        connection.execute(
            text(
                """
                INSERT INTO repository_analysis_result (
                    github_repository_id,
                    source_provider,
                    source_kind,
                    source_metadata,
                    monetization_potential,
                    pros,
                    cons,
                    missing_feature_signals,
                    analyzed_at
                ) VALUES (
                    :github_repository_id,
                    :source_provider,
                    :source_kind,
                    :source_metadata,
                    :monetization_potential,
                    :pros,
                    :cons,
                    :missing_feature_signals,
                    :analyzed_at
                )
                """
            ),
            {
                "github_repository_id": 987654321,
                "source_provider": "github",
                "source_kind": "repository_readme",
                "source_metadata": '{"readme_artifact_path":"data/readmes/987654321.md"}',
                "monetization_potential": "high",
                "pros": '["Clear API story"]',
                "cons": '["Pricing unclear"]',
                "missing_feature_signals": '["Missing billing detail"]',
                "analyzed_at": "2026-03-08 13:45:00+00:00",
            },
        )

        analysis_row = connection.execute(
            text(
                """
                SELECT source_provider, source_kind, source_metadata, monetization_potential,
                       pros, cons, missing_feature_signals, analyzed_at
                FROM repository_analysis_result
                WHERE github_repository_id = :github_repository_id
                """
            ),
            {"github_repository_id": 987654321},
        ).one()
        assert analysis_row.source_provider == "github"
        assert analysis_row.source_kind == "repository_readme"
        assert analysis_row.source_metadata == (
            '{"readme_artifact_path":"data/readmes/987654321.md"}'
        )
        assert analysis_row.monetization_potential == "high"
        assert analysis_row.pros == '["Clear API story"]'
        assert analysis_row.cons == '["Pricing unclear"]'
        assert analysis_row.missing_feature_signals == '["Missing billing detail"]'
        assert str(analysis_row.analyzed_at).startswith("2026-03-08 13:45:00")

        connection.execute(
            text(
                """
                INSERT INTO repository_artifact (
                    github_repository_id,
                    artifact_kind,
                    runtime_relative_path,
                    content_sha256,
                    byte_size,
                    content_type,
                    source_kind,
                    source_url,
                    provenance_metadata,
                    generated_at
                ) VALUES (
                    :github_repository_id,
                    :artifact_kind,
                    :runtime_relative_path,
                    :content_sha256,
                    :byte_size,
                    :content_type,
                    :source_kind,
                    :source_url,
                    :provenance_metadata,
                    :generated_at
                )
                """
            ),
            {
                "github_repository_id": 987654321,
                "artifact_kind": "readme_snapshot",
                "runtime_relative_path": "data/readmes/987654321.md",
                "content_sha256": "a" * 64,
                "byte_size": 512,
                "content_type": "text/markdown; charset=utf-8",
                "source_kind": "repository_readme",
                "source_url": "https://api.github.com/repos/octocat/hello-world/readme",
                "provenance_metadata": '{"normalization_version":"story-3.4-v1"}',
                "generated_at": "2026-03-08 13:45:00+00:00",
            },
        )

        artifact_row = connection.execute(
            text(
                """
                SELECT artifact_kind, runtime_relative_path, content_sha256, byte_size,
                       content_type, source_kind, source_url, provenance_metadata, generated_at
                FROM repository_artifact
                WHERE github_repository_id = :github_repository_id
                """
            ),
            {"github_repository_id": 987654321},
        ).one()
        assert artifact_row.artifact_kind == "readme_snapshot"
        assert artifact_row.runtime_relative_path == "data/readmes/987654321.md"
        assert artifact_row.content_sha256 == "a" * 64
        assert artifact_row.byte_size == 512
        assert artifact_row.content_type == "text/markdown; charset=utf-8"
        assert artifact_row.source_kind == "repository_readme"
        assert artifact_row.source_url == "https://api.github.com/repos/octocat/hello-world/readme"
        assert artifact_row.provenance_metadata == '{"normalization_version":"story-3.4-v1"}'
        assert str(artifact_row.generated_at).startswith("2026-03-08 13:45:00")

        with pytest.raises(IntegrityError, match="UNIQUE constraint failed: repository_intake.github_repository_id|UNIQUE constraint failed: repository_intake.full_name|PRIMARY KEY must be unique"):
            connection.execute(
                text(
                    """
                    INSERT INTO repository_intake (
                        github_repository_id,
                        owner_login,
                        repository_name,
                        full_name
                    ) VALUES (
                        :github_repository_id,
                        :owner_login,
                        :repository_name,
                        :full_name
                    )
                    """
                ),
                {
                    "github_repository_id": 987654321,
                    "owner_login": "duplicate-owner",
                    "repository_name": "duplicate-repo",
                    "full_name": "duplicate-owner/duplicate-repo",
                },
            )


def test_repository_intake_migration_rejects_invalid_queue_status(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "enum-constraint.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        with pytest.raises(IntegrityError, match="repository_queue_status|CHECK constraint failed"):
            connection.execute(
                text(
                    """
                    INSERT INTO repository_intake (
                        github_repository_id,
                        owner_login,
                        repository_name,
                        full_name,
                        queue_status
                    ) VALUES (
                        :github_repository_id,
                        :owner_login,
                        :repository_name,
                        :full_name,
                        :queue_status
                    )
                    """
                ),
                {
                    "github_repository_id": 111111,
                    "owner_login": "octocat",
                    "repository_name": "hello-world",
                    "full_name": "octocat/hello-world",
                    "queue_status": "invalid_status",
                },
            )


def test_backfill_progress_migration_accepts_and_reads_checkpoint_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "backfill-progress.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO backfill_progress (
                    source_provider,
                    window_start_date,
                    created_before_boundary,
                    created_before_cursor,
                    next_page,
                    pages_processed_in_run,
                    exhausted
                ) VALUES (
                    :source_provider,
                    :window_start_date,
                    :created_before_boundary,
                    :created_before_cursor,
                    :next_page,
                    :pages_processed_in_run,
                    :exhausted
                )
                """
            ),
            {
                "source_provider": "github",
                "window_start_date": "2026-02-01",
                "created_before_boundary": "2026-03-01",
                "created_before_cursor": "2026-02-20 12:00:00+00:00",
                "next_page": 3,
                "pages_processed_in_run": 2,
                "exhausted": 0,
            },
        )

        row = connection.execute(
            text(
                """
                SELECT
                    source_provider,
                    window_start_date,
                    created_before_boundary,
                    created_before_cursor,
                    next_page,
                    pages_processed_in_run,
                    exhausted
                FROM backfill_progress
                WHERE source_provider = :source_provider
                """
            ),
            {"source_provider": "github"},
        ).one()

    assert row.source_provider == "github"
    assert str(row.window_start_date) == "2026-02-01"
    assert str(row.created_before_boundary) == "2026-03-01"
    assert str(row.created_before_cursor).startswith("2026-02-20 12:00:00")
    assert row.next_page == 3
    assert row.pages_processed_in_run == 2
    assert row.exhausted == 0


def test_backfill_progress_migration_rejects_invalid_windows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "backfill-progress-invalid.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        with pytest.raises(IntegrityError, match="ck_backfill_progress_next_page_positive|CHECK constraint failed"):
            connection.execute(
                text(
                    """
                    INSERT INTO backfill_progress (
                        source_provider,
                        window_start_date,
                        created_before_boundary,
                        next_page,
                        exhausted
                    ) VALUES (
                        :source_provider,
                        :window_start_date,
                        :created_before_boundary,
                        :next_page,
                        :exhausted
                    )
                    """
                ),
                {
                    "source_provider": "github",
                    "window_start_date": "2026-03-01",
                    "created_before_boundary": "2026-03-01",
                    "next_page": 0,
                    "exhausted": 0,
                },
            )


def test_backfill_resume_required_migration_preserves_legacy_resume_state(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "backfill-resume-required.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_build_alembic_config(database_url), "20260308_0005")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO backfill_progress (
                    source_provider,
                    window_start_date,
                    created_before_boundary,
                    created_before_cursor,
                    next_page,
                    exhausted,
                    last_checkpointed_at
                ) VALUES (
                    :source_provider,
                    :window_start_date,
                    :created_before_boundary,
                    :created_before_cursor,
                    :next_page,
                    :exhausted,
                    :last_checkpointed_at
                )
                """
            ),
            {
                "source_provider": "github",
                "window_start_date": "2026-02-01",
                "created_before_boundary": "2026-03-01",
                "created_before_cursor": None,
                "next_page": 3,
                "exhausted": 0,
                "last_checkpointed_at": "2026-03-08 12:00:00+00:00",
            },
        )
    command.upgrade(_build_alembic_config(database_url), "head")

    with engine.begin() as connection:
        row = connection.execute(
            text(
                """
                SELECT resume_required, pages_processed_in_run
                FROM backfill_progress
                WHERE source_provider = :source_provider
                """
            ),
            {"source_provider": "github"},
        ).one()

    assert row.resume_required == 1
    assert row.pages_processed_in_run == 2


def test_firehose_progress_migration_accepts_resume_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "firehose-progress.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO firehose_progress (
                    source_provider,
                    active_mode,
                    next_page,
                    pages_processed_in_run,
                    new_anchor_date,
                    trending_anchor_date,
                    run_started_at,
                    resume_required,
                    last_checkpointed_at
                ) VALUES (
                    :source_provider,
                    :active_mode,
                    :next_page,
                    :pages_processed_in_run,
                    :new_anchor_date,
                    :trending_anchor_date,
                    :run_started_at,
                    :resume_required,
                    :last_checkpointed_at
                )
                """
            ),
            {
                "source_provider": "github",
                "active_mode": "trending",
                "next_page": 3,
                "pages_processed_in_run": 2,
                "new_anchor_date": "2026-03-07",
                "trending_anchor_date": "2026-03-01",
                "run_started_at": "2026-03-08 12:00:00+00:00",
                "resume_required": 1,
                "last_checkpointed_at": "2026-03-08 12:10:00+00:00",
            },
        )

        row = connection.execute(
            text(
                """
                SELECT
                    active_mode,
                    next_page,
                    pages_processed_in_run,
                    new_anchor_date,
                    trending_anchor_date,
                    resume_required
                FROM firehose_progress
                WHERE source_provider = :source_provider
                """
            ),
            {"source_provider": "github"},
        ).one()

    assert row.active_mode == "trending"
    assert row.next_page == 3
    assert row.pages_processed_in_run == 2
    assert str(row.new_anchor_date) == "2026-03-07"
    assert str(row.trending_anchor_date) == "2026-03-01"
    assert row.resume_required == 1


def test_firehose_progress_migration_rejects_incomplete_resume_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "firehose-progress-invalid.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        with pytest.raises(IntegrityError, match="ck_firehose_progress_resume_state_complete|CHECK constraint failed"):
            connection.execute(
                text(
                    """
                    INSERT INTO firehose_progress (
                        source_provider,
                        next_page,
                        resume_required
                    ) VALUES (
                        :source_provider,
                        :next_page,
                        :resume_required
                    )
                    """
                ),
                {
                    "source_provider": "github",
                    "next_page": 1,
                    "resume_required": 1,
                },
            )


def test_repository_intake_migration_accepts_firehose_mode_for_firehose_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "firehose-mode.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO repository_intake (
                    github_repository_id,
                    owner_login,
                    repository_name,
                    full_name,
                    discovery_source,
                    firehose_discovery_mode
                ) VALUES (
                    :github_repository_id,
                    :owner_login,
                    :repository_name,
                    :full_name,
                    :discovery_source,
                    :firehose_discovery_mode
                )
                """
            ),
            {
                "github_repository_id": 222223,
                "owner_login": "octocat",
                "repository_name": "firehose-repo",
                "full_name": "octocat/firehose-repo",
                "discovery_source": "firehose",
                "firehose_discovery_mode": "new",
            },
        )

        row = connection.execute(
            text(
                """
                SELECT discovery_source, firehose_discovery_mode
                FROM repository_intake
                WHERE github_repository_id = :github_repository_id
                """
            ),
            {"github_repository_id": 222223},
        ).one()

    assert row.discovery_source == "firehose"
    assert row.firehose_discovery_mode == "new"


def test_repository_intake_migration_rejects_firehose_rows_without_firehose_mode(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "missing-firehose-mode.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        with pytest.raises(IntegrityError, match="ck_repository_intake_firehose_mode_matches_discovery_source|CHECK constraint failed"):
            connection.execute(
                text(
                    """
                    INSERT INTO repository_intake (
                        github_repository_id,
                        owner_login,
                        repository_name,
                        full_name,
                        discovery_source
                    ) VALUES (
                        :github_repository_id,
                        :owner_login,
                        :repository_name,
                        :full_name,
                        :discovery_source
                    )
                    """
                ),
                {
                    "github_repository_id": 222224,
                    "owner_login": "octocat",
                    "repository_name": "broken-firehose-repo",
                    "full_name": "octocat/broken-firehose-repo",
                    "discovery_source": "firehose",
                },
            )


def test_repository_intake_migration_timestamps_are_utc_aware(
    tmp_path: Path,
) -> None:
    from app.models import RepositoryIntake

    database_path = tmp_path / "timestamp-utc.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    record = RepositoryIntake(
        github_repository_id=222222,
        owner_login="ts-owner",
        repository_name="ts-repo",
        full_name="ts-owner/ts-repo",
    )
    with SQLModelSession(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)

    assert record.discovered_at.tzinfo is not None, (
        "discovered_at must be UTC-aware; got naive datetime"
    )
    assert record.queue_created_at.tzinfo is not None, (
        "queue_created_at must be UTC-aware; got naive datetime"
    )
    assert record.status_updated_at.tzinfo is not None, (
        "status_updated_at must be UTC-aware; got naive datetime"
    )
    assert record.discovered_at.tzinfo == timezone.utc
    assert record.queue_created_at.tzinfo == timezone.utc
    assert record.status_updated_at.tzinfo == timezone.utc


def test_repository_intake_migration_lifecycle_timestamps_are_utc_aware(
    tmp_path: Path,
) -> None:
    from app.models import RepositoryIntake

    database_path = tmp_path / "lifecycle-utc.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    record = RepositoryIntake(
        github_repository_id=333333,
        owner_login="lc-owner",
        repository_name="lc-repo",
        full_name="lc-owner/lc-repo",
        processing_started_at=now,
        processing_completed_at=now,
        last_failed_at=now,
    )
    with SQLModelSession(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)

    assert record.processing_started_at is not None
    assert record.processing_started_at.tzinfo == timezone.utc, (
        "processing_started_at must be UTC-aware; got naive datetime"
    )
    assert record.processing_completed_at is not None
    assert record.processing_completed_at.tzinfo == timezone.utc, (
        "processing_completed_at must be UTC-aware; got naive datetime"
    )
    assert record.last_failed_at is not None
    assert record.last_failed_at.tzinfo == timezone.utc, (
        "last_failed_at must be UTC-aware; got naive datetime"
    )


def test_repository_intake_migration_rejects_invalid_source_provider(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "invalid-provider.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        with pytest.raises(IntegrityError, match="ck_repository_intake_source_provider_valid|CHECK constraint failed"):
            connection.execute(
                text(
                    "INSERT INTO repository_intake "
                    "(github_repository_id, owner_login, repository_name, full_name, source_provider) "
                    "VALUES (:github_repository_id, :owner_login, :repository_name, :full_name, :source_provider)"
                ),
                {
                    "github_repository_id": 600001,
                    "owner_login": "octocat",
                    "repository_name": "hello-world",
                    "full_name": "octocat/hello-world",
                    "source_provider": "definitely-not-github",
                },
            )


def test_repository_intake_migration_rejects_blank_metadata(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "blank-metadata.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        for blank_field, params, expected_constraint in [
            (
                "owner_login",
                {"github_repository_id": 400001, "owner_login": "", "repository_name": "r", "full_name": "/r"},
                "ck_repository_intake_owner_login_not_blank|CHECK constraint failed",
            ),
            (
                "repository_name",
                {"github_repository_id": 400002, "owner_login": "o", "repository_name": "", "full_name": "o/"},
                "ck_repository_intake_repository_name_not_blank|CHECK constraint failed",
            ),
            (
                "full_name",
                {"github_repository_id": 400003, "owner_login": "o", "repository_name": "r", "full_name": ""},
                "ck_repository_intake_full_name_not_blank|CHECK constraint failed",
            ),
        ]:
            with pytest.raises(IntegrityError, match=expected_constraint):
                connection.execute(
                    text(
                        "INSERT INTO repository_intake "
                        "(github_repository_id, owner_login, repository_name, full_name) "
                        "VALUES (:github_repository_id, :owner_login, :repository_name, :full_name)"
                    ),
                    params,
                )


def test_repository_intake_migration_rejects_inconsistent_full_name(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "inconsistent-full-name.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        with pytest.raises(IntegrityError, match="ck_repository_intake_full_name_consistent|CHECK constraint failed"):
            connection.execute(
                text(
                    "INSERT INTO repository_intake "
                    "(github_repository_id, owner_login, repository_name, full_name) "
                    "VALUES (:github_repository_id, :owner_login, :repository_name, :full_name)"
                ),
                {
                    "github_repository_id": 500001,
                    "owner_login": "octocat",
                    "repository_name": "hello-world",
                    "full_name": "wrong/full-name",
                },
            )

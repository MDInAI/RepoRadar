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
    assert inspector.get_pk_constraint("repository_intake")["constrained_columns"] == [
        "github_repository_id"
    ]

    columns = {column["name"]: column for column in inspector.get_columns("repository_intake")}
    assert {
        "github_repository_id",
        "source_provider",
        "owner_login",
        "repository_name",
        "full_name",
        "discovery_source",
        "queue_status",
        "discovered_at",
        "queue_created_at",
        "status_updated_at",
        "processing_started_at",
        "processing_completed_at",
        "last_failed_at",
    } <= set(columns)

    assert not columns["github_repository_id"]["nullable"]
    assert not columns["queue_status"]["nullable"]
    assert not columns["status_updated_at"]["nullable"]

    assert {index["name"] for index in inspector.get_indexes("repository_intake")} == {
        "ix_repository_intake_discovery_source",
        "ix_repository_intake_full_name",
        "ix_repository_intake_queue_status",
    }

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
                SELECT source_provider, discovery_source, queue_status
                FROM repository_intake
                WHERE github_repository_id = :github_repository_id
                """
            ),
            {"github_repository_id": 987654321},
        ).one()

        assert row.source_provider == "github"
        assert row.discovery_source == "unknown"
        assert row.queue_status == "pending"

        with pytest.raises(IntegrityError):
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
        with pytest.raises(IntegrityError):
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
        with pytest.raises(IntegrityError):
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
        for blank_field, params in [
            (
                "owner_login",
                {"github_repository_id": 400001, "owner_login": "", "repository_name": "r", "full_name": "/r"},
            ),
            (
                "repository_name",
                {"github_repository_id": 400002, "owner_login": "o", "repository_name": "", "full_name": "o/"},
            ),
            (
                "full_name",
                {"github_repository_id": 400003, "owner_login": "o", "repository_name": "r", "full_name": ""},
            ),
        ]:
            with pytest.raises(IntegrityError, match=".*"):
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
        with pytest.raises(IntegrityError):
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

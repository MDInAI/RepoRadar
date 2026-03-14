from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def _build_alembic_config(database_url: str) -> Config:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_agent_event_migration_creates_tables_indexes_and_defaults(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'agent-events.db'}"
    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)

    assert "agent_runs" in inspector.get_table_names()
    assert "system_events" in inspector.get_table_names()
    assert {index["name"] for index in inspector.get_indexes("agent_runs")} == {
        "ix_agent_runs_agent_name",
        "ix_agent_runs_started_at",
        "ix_agent_runs_status",
    }
    assert {index["name"] for index in inspector.get_indexes("system_events")} == {
        "ix_system_events_agent_name",
        "ix_system_events_agent_run_id",
        "ix_system_events_created_at",
        "ix_system_events_event_type",
        "ix_system_events_failure_classification",
        "ix_system_events_failure_severity",
    }
    foreign_keys = inspector.get_foreign_keys("system_events")
    assert any(
        fk["constrained_columns"] == ["affected_repository_id"]
        and fk["referred_table"] == "repository_intake"
        and fk["referred_columns"] == ["github_repository_id"]
        for fk in foreign_keys
    )

    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO agent_runs (agent_name) VALUES ('firehose')")
        )
        connection.execute(
            text(
                """
                INSERT INTO system_events (
                    event_type,
                    agent_name,
                    message,
                    agent_run_id
                ) VALUES (
                    'agent_started',
                    'firehose',
                    'firehose run started.',
                    1
                )
                """
            )
        )

        run_row = connection.execute(
            text(
                """
                SELECT status, items_processed, items_succeeded, items_failed
                FROM agent_runs
                WHERE id = 1
                """
            )
        ).one()
        event_row = connection.execute(
            text(
                """
                SELECT severity, context_json
                FROM system_events
                WHERE id = 1
                """
            )
        ).one()

    assert run_row.status == "running"
    assert run_row.items_processed is None
    assert run_row.items_succeeded is None
    assert run_row.items_failed is None
    assert event_row.severity == "info"
    assert event_row.context_json is None


def test_agent_event_migration_downgrade_backfills_nullable_counts(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'agent-events-downgrade.db'}"
    config = _build_alembic_config(database_url)
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO agent_runs (
                    agent_name,
                    status,
                    items_processed,
                    items_succeeded,
                    items_failed
                ) VALUES (
                    'firehose',
                    'failed',
                    NULL,
                    NULL,
                    NULL
                )
                """
            )
        )

    command.downgrade(config, "20260310_0013")

    downgraded_engine = create_engine(database_url)
    inspector = inspect(downgraded_engine)
    columns = {column["name"]: column for column in inspector.get_columns("agent_runs")}

    with downgraded_engine.begin() as connection:
        run_row = connection.execute(
            text(
                """
                SELECT items_processed, items_succeeded, items_failed
                FROM agent_runs
                WHERE id = 1
                """
            )
        ).one()

    assert columns["items_processed"]["nullable"] is False
    assert columns["items_succeeded"]["nullable"] is False
    assert columns["items_failed"]["nullable"] is False
    assert run_row.items_processed == 0
    assert run_row.items_succeeded == 0
    assert run_row.items_failed == 0


def test_upstream_provider_constraint_enforces_valid_values(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'upstream-provider-constraint.db'}"
    command.upgrade(_build_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO system_events (
                    event_type, agent_name, message, upstream_provider
                ) VALUES ('test', 'analyst', 'valid github', 'github')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO system_events (
                    event_type, agent_name, message, upstream_provider
                ) VALUES ('test', 'analyst', 'valid llm', 'llm')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO system_events (
                    event_type, agent_name, message, upstream_provider
                ) VALUES ('test', 'analyst', 'null is valid', NULL)
                """
            )
        )

        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO system_events (
                        event_type, agent_name, message, upstream_provider
                    ) VALUES ('test', 'analyst', 'invalid value', 'invalid')
                    """
                )
            )

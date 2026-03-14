from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models import AgentRun, AgentRunStatus, EventSeverity, SystemEvent


def test_agent_run_defaults_capture_durable_status_shape() -> None:
    record = AgentRun(agent_name="firehose")

    assert record.agent_name == "firehose"
    assert record.status is AgentRunStatus.RUNNING
    assert record.started_at.tzinfo == timezone.utc
    assert record.completed_at is None
    assert record.duration_seconds is None
    assert record.items_processed is None
    assert record.items_succeeded is None
    assert record.items_failed is None
    assert record.error_summary is None
    assert record.error_context is None

    table = AgentRun.__table__
    assert table.c.status.type.enums == [status.value for status in AgentRunStatus]
    assert {index.name for index in table.indexes} == {
        "ix_agent_runs_agent_name",
        "ix_agent_runs_started_at",
        "ix_agent_runs_status",
    }


def test_system_event_defaults_capture_event_snapshot_shape() -> None:
    created_at = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    record = SystemEvent(
        event_type="agent_started",
        agent_name="analyst",
        severity=EventSeverity.INFO,
        message="analyst run started",
        created_at=created_at,
    )

    assert record.event_type == "agent_started"
    assert record.agent_name == "analyst"
    assert record.severity is EventSeverity.INFO
    assert record.message == "analyst run started"
    assert record.context_json is None
    assert record.agent_run_id is None
    assert record.created_at == created_at

    table = SystemEvent.__table__
    assert table.c.severity.type.enums == [severity.value for severity in EventSeverity]
    assert {index.name for index in table.indexes} == {
        "ix_system_events_agent_name",
        "ix_system_events_agent_run_id",
        "ix_system_events_created_at",
        "ix_system_events_event_type",
        "ix_system_events_failure_classification",
        "ix_system_events_failure_severity",
    }


def test_agent_run_and_event_enums_reject_invalid_values() -> None:
    with pytest.raises(ValueError):
        AgentRunStatus("unknown")

    with pytest.raises(ValueError):
        EventSeverity("debug")

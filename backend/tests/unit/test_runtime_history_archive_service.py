from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from sqlmodel import select

from app.models import AgentRun, AgentRunStatus, EventSeverity, SystemEvent
from app.services.runtime_history_archive_service import RuntimeHistoryArchiveService


def test_archive_system_events_exports_and_deletes_old_rows(session, tmp_path: Path) -> None:
    old_event = SystemEvent(
        event_type="agent_failed",
        agent_name="analyst",
        severity=EventSeverity.ERROR,
        message="Old Analyst error",
        created_at=datetime.now(timezone.utc) - timedelta(days=45),
    )
    fresh_event = SystemEvent(
        event_type="agent_completed",
        agent_name="firehose",
        severity=EventSeverity.INFO,
        message="Fresh Firehose success",
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    session.add(old_event)
    session.add(fresh_event)
    session.commit()

    service = RuntimeHistoryArchiveService(session, tmp_path / "runtime")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result = service.archive_system_events(older_than=cutoff)

    remaining = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert result.exported_count == 1
    assert result.deleted_count == 1
    assert result.archive_path is not None
    assert result.archive_path.exists()
    assert len(remaining) == 1
    assert remaining[0].message == "Fresh Firehose success"

    lines = result.archive_path.read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[0])
    assert payload["entity"] == "system_events"
    assert payload["record"]["message"] == "Old Analyst error"


def test_archive_agent_runs_skips_running_rows_and_exports_terminal_rows(
    session,
    tmp_path: Path,
) -> None:
    old_completed_run = AgentRun(
        agent_name="backfill",
        status=AgentRunStatus.COMPLETED,
        started_at=datetime.now(timezone.utc) - timedelta(days=60),
        completed_at=datetime.now(timezone.utc) - timedelta(days=60, minutes=-2),
        items_processed=100,
    )
    old_running_run = AgentRun(
        agent_name="analyst",
        status=AgentRunStatus.RUNNING,
        started_at=datetime.now(timezone.utc) - timedelta(days=60),
    )
    fresh_failed_run = AgentRun(
        agent_name="firehose",
        status=AgentRunStatus.FAILED,
        started_at=datetime.now(timezone.utc) - timedelta(days=2),
        completed_at=datetime.now(timezone.utc) - timedelta(days=2, minutes=-1),
    )
    session.add(old_completed_run)
    session.add(old_running_run)
    session.add(fresh_failed_run)
    session.commit()

    service = RuntimeHistoryArchiveService(session, tmp_path / "runtime")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result = service.archive_agent_runs(older_than=cutoff)

    remaining = session.exec(select(AgentRun).order_by(AgentRun.id)).all()

    assert result.exported_count == 1
    assert result.deleted_count == 1
    assert result.archive_path is not None
    assert result.archive_path.exists()
    assert [row.status for row in remaining] == [AgentRunStatus.RUNNING, AgentRunStatus.FAILED]

    lines = result.archive_path.read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[0])
    assert payload["entity"] == "agent_runs"
    assert payload["record"]["agent_name"] == "backfill"


def test_archive_operational_history_uses_retention_windows(session, tmp_path: Path) -> None:
    session.add(
        SystemEvent(
            event_type="agent_failed",
            agent_name="analyst",
            severity=EventSeverity.ERROR,
            message="Archive me",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    session.add(
        AgentRun(
            agent_name="bouncer",
            status=AgentRunStatus.COMPLETED,
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
        )
    )
    session.commit()

    service = RuntimeHistoryArchiveService(session, tmp_path / "runtime")
    result = service.archive_operational_history(
        event_retention_days=30,
        run_retention_days=30,
        now=datetime(2026, 3, 17, tzinfo=timezone.utc),
    )

    assert result.system_events.exported_count == 1
    assert result.agent_runs.exported_count == 1

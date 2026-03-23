from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel import Session, create_engine, select

from agentic_workers.core.recovery import validate_startup_recovery
from agentic_workers.storage.backend_models import (
    AgentRun,
    AgentRunStatus,
    AgentPauseState,
    EventSeverity,
    FailureClassification,
    SQLModel,
    SystemEvent,
)


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_validate_startup_recovery_auto_resumes_stale_backfill_timeout_pause() -> None:
    with _build_session() as session:
        triggering_event = SystemEvent(
            event_type="repository_discovery_failed",
            agent_name="backfill",
            severity=EventSeverity.CRITICAL,
            message="backfill encountered an unexpected runtime failure.",
            context_json=json.dumps(
                {
                    "error": "The read operation timed out",
                    "page": 1,
                    "window_start_date": "2020-10-09",
                },
                sort_keys=True,
            ),
            failure_classification=FailureClassification.BLOCKING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(triggering_event)
        session.commit()
        session.refresh(triggering_event)

        pause_state = AgentPauseState(
            agent_name="backfill",
            is_paused=True,
            paused_at=datetime.now(timezone.utc),
            pause_reason="Blocking failure in backfill",
            resume_condition="Operator review required",
            triggered_by_event_id=triggering_event.id,
        )
        session.add(pause_state)
        session.commit()

        validate_startup_recovery(session)

        session.refresh(pause_state)
        assert pause_state.is_paused is False
        assert pause_state.resumed_by == "auto"
        assert pause_state.triggered_by_event_id is None

        resume_events = session.exec(
            select(SystemEvent)
            .where(SystemEvent.agent_name == "backfill")
            .where(SystemEvent.event_type == "agent_resumed")
        ).all()
        assert len(resume_events) == 1
        assert "auto-resumed" in resume_events[0].message


def test_validate_startup_recovery_keeps_true_blocking_pause() -> None:
    with _build_session() as session:
        triggering_event = SystemEvent(
            event_type="repository_discovery_failed",
            agent_name="backfill",
            severity=EventSeverity.CRITICAL,
            message="backfill encountered an unexpected runtime failure.",
            context_json=json.dumps(
                {
                    "error": "GitHub request failed with status 401: Unauthorized",
                    "page": 1,
                },
                sort_keys=True,
            ),
            failure_classification=FailureClassification.BLOCKING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(triggering_event)
        session.commit()
        session.refresh(triggering_event)

        pause_state = AgentPauseState(
            agent_name="backfill",
            is_paused=True,
            paused_at=datetime.now(timezone.utc),
            pause_reason="Blocking failure in backfill",
            resume_condition="Operator review required",
            triggered_by_event_id=triggering_event.id,
        )
        session.add(pause_state)
        session.commit()

        validate_startup_recovery(session)

        session.refresh(pause_state)
        assert pause_state.is_paused is True

        resume_events = session.exec(
            select(SystemEvent)
            .where(SystemEvent.agent_name == "backfill")
            .where(SystemEvent.event_type == "agent_resumed")
        ).all()
        assert resume_events == []


def test_validate_startup_recovery_marks_stale_running_backfill_run_failed() -> None:
    with _build_session() as session:
        running_run = AgentRun(
            agent_name="backfill",
            status=AgentRunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        session.add(running_run)
        session.commit()
        session.refresh(running_run)

        validate_startup_recovery(session)

        session.refresh(running_run)
        assert running_run.status is AgentRunStatus.FAILED
        assert running_run.completed_at is not None
        assert running_run.error_summary == "Recovered stale running job during worker startup."

        recovery_events = session.exec(
            select(SystemEvent)
            .where(SystemEvent.agent_name == "backfill")
            .where(SystemEvent.event_type == "worker_recovered")
            .order_by(SystemEvent.id.asc())
        ).all()
        assert recovery_events
        assert "Recovered stale active backfill run" in recovery_events[0].message

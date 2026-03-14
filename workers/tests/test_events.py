from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, create_engine, select

from agentic_workers.core.events import (
    complete_agent_run,
    emit_event,
    emit_failure_event,
    fail_agent_run,
    pause_event_run_id,
    skip_agent_run,
    start_agent_run,
)
from agentic_workers.storage.backend_models import (
    AgentRun,
    AgentRunStatus,
    EventSeverity,
    FailureClassification,
    FailureSeverity,
    SQLModel,
    SystemEvent,
)


def _make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'events.db'}")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_start_agent_run_creates_run_and_started_event(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        run_id = start_agent_run(session, "firehose")
        run = session.get(AgentRun, run_id)
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert run is not None
    assert run.status is AgentRunStatus.RUNNING
    assert [event.event_type for event in events] == ["agent_started"]


def test_complete_agent_run_updates_status_and_emits_completion_event(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        run_id = start_agent_run(session, "analyst")
        complete_agent_run(session, run_id, items_processed=3, items_succeeded=2, items_failed=1)
        run = session.get(AgentRun, run_id)
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert run is not None
    assert run.status is AgentRunStatus.COMPLETED
    assert run.completed_at is not None
    assert run.duration_seconds is not None
    assert run.items_processed == 3
    assert [event.event_type for event in events] == ["agent_started", "agent_completed"]


def test_fail_agent_run_records_error_context_and_failed_event(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        run_id = start_agent_run(session, "backfill")
        fail_agent_run(
            session,
            run_id,
            error_summary="backfill crashed",
            error_context='{"traceback": "boom"}',
            items_processed=4,
            items_succeeded=1,
            items_failed=3,
        )
        run = session.get(AgentRun, run_id)
        failed_event = session.exec(
            select(SystemEvent).where(SystemEvent.event_type == "agent_failed")
        ).one()

    assert run is not None
    assert run.status is AgentRunStatus.FAILED
    assert run.error_context == '{"traceback": "boom"}'
    assert failed_event.severity is EventSeverity.ERROR
    assert failed_event.message == "backfill crashed"


def test_start_agent_run_rolls_back_if_started_event_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with _make_session(tmp_path) as session:
        original_add = session.add

        def failing_add(instance: object) -> None:
            if isinstance(instance, SystemEvent):
                raise RuntimeError("cannot persist started event")
            original_add(instance)

        monkeypatch.setattr(session, "add", failing_add)

        with pytest.raises(RuntimeError, match="cannot persist started event"):
            start_agent_run(session, "firehose")

        assert session.exec(select(AgentRun)).all() == []
        assert session.exec(select(SystemEvent)).all() == []


def test_complete_agent_run_rolls_back_if_completion_event_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with _make_session(tmp_path) as session:
        run_id = start_agent_run(session, "analyst")
        original_add = session.add

        def failing_add(instance: object) -> None:
            if isinstance(instance, SystemEvent) and instance.event_type == "agent_completed":
                raise RuntimeError("cannot persist completion event")
            original_add(instance)

        monkeypatch.setattr(session, "add", failing_add)

        with pytest.raises(RuntimeError, match="cannot persist completion event"):
            complete_agent_run(session, run_id, items_processed=3, items_succeeded=2, items_failed=1)

        session.expire_all()
        run = session.get(AgentRun, run_id)
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert run is not None
    assert run.status is AgentRunStatus.RUNNING
    assert [event.event_type for event in events] == ["agent_started"]


def test_skip_agent_run_creates_skipped_run_and_event(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        skip_agent_run(session, "firehose", "firehose is paused")
        run = session.exec(select(AgentRun)).one()
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert run.status is AgentRunStatus.SKIPPED
    assert run.error_summary == "firehose is paused"
    assert [event.event_type for event in events] == ["agent_skipped"]


def test_emit_event_persists_custom_operational_event(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        run_id = start_agent_run(session, "bouncer")
        emit_event(
            session,
            event_type="milestone",
            agent_name="bouncer",
            severity="warning",
            message="processed 100 repositories",
            context_json='{"count": 100}',
            agent_run_id=run_id,
        )
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert [event.event_type for event in events] == ["agent_started", "milestone"]
    assert events[-1].context_json == '{"count": 100}'


def test_emit_failure_event_defers_commit_to_the_caller(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        run_id = start_agent_run(session, "firehose")
        emit_failure_event(
            session,
            event_type="repository_discovery_failed",
            agent_name="firehose",
            message="github transport failed",
            classification=FailureClassification.RETRYABLE,
            failure_severity=FailureSeverity.WARNING,
            upstream_provider="github",
            agent_run_id=run_id,
        )

        # The failure event should still be pending until the caller commits.
        session.rollback()
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert [event.event_type for event in events] == ["agent_started"]


def test_pause_event_run_id_only_keeps_the_triggering_agents_run() -> None:
    assert (
        pause_event_run_id(
            triggering_agent_name="firehose",
            affected_agent_name="firehose",
            triggering_run_id=17,
        )
        == 17
    )
    assert (
        pause_event_run_id(
            triggering_agent_name="firehose",
            affected_agent_name="backfill",
            triggering_run_id=17,
        )
        is None
    )

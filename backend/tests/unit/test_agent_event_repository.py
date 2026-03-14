from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import AgentPauseState, AgentRun, AgentRunStatus, EventSeverity, SystemEvent
from app.repositories.agent_event_repository import (
    AgentEventRepository,
    AgentRunListFilters,
    SystemEventListFilters,
)


def _make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_agent_event_repository_creates_completes_and_filters_agent_runs() -> None:
    with _make_session() as session:
        repository = AgentEventRepository(session)
        created = repository.create_agent_run("firehose")

        completed = repository.complete_agent_run(
            created.id,
            status=AgentRunStatus.COMPLETED,
            items_processed=8,
            items_succeeded=7,
            items_failed=1,
            error_summary=None,
            error_context=None,
        )

        filtered = repository.list_agent_runs(
            AgentRunListFilters(agent_name="firehose", status=AgentRunStatus.COMPLETED, limit=10)
        )

    assert created.id is not None
    assert completed.completed_at is not None
    assert completed.duration_seconds is not None
    assert completed.items_processed == 8
    assert [record.id for record in filtered] == [created.id]


def test_agent_event_repository_lists_system_events_and_latest_runs() -> None:
    with _make_session() as session:
        session.add_all(
            [
                AgentRun(
                    id=1,
                    agent_name="firehose",
                    status=AgentRunStatus.COMPLETED,
                    started_at=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 3, 10, 10, 5, tzinfo=timezone.utc),
                    duration_seconds=300.0,
                    items_processed=10,
                    items_succeeded=10,
                    items_failed=0,
                ),
                AgentRun(
                    id=2,
                    agent_name="firehose",
                    status=AgentRunStatus.FAILED,
                    started_at=datetime(2026, 3, 10, 11, 0, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 3, 10, 11, 5, tzinfo=timezone.utc),
                    duration_seconds=300.0,
                    items_processed=5,
                    items_succeeded=3,
                    items_failed=2,
                    error_summary="boom",
                ),
                AgentRun(
                    id=3,
                    agent_name="analyst",
                    status=AgentRunStatus.COMPLETED,
                    started_at=datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 3, 10, 9, 2, tzinfo=timezone.utc),
                    duration_seconds=120.0,
                    items_processed=2,
                    items_succeeded=2,
                    items_failed=0,
                ),
            ]
        )
        session.add_all(
            [
                SystemEvent(
                    event_type="agent_failed",
                    agent_name="firehose",
                    severity=EventSeverity.ERROR,
                    message="boom",
                    agent_run_id=2,
                    created_at=datetime(2026, 3, 10, 11, 5, tzinfo=timezone.utc),
                ),
                SystemEvent(
                    event_type="agent_completed",
                    agent_name="analyst",
                    severity=EventSeverity.INFO,
                    message="analyst done",
                    agent_run_id=3,
                    created_at=datetime(2026, 3, 10, 9, 2, tzinfo=timezone.utc),
                ),
            ]
        )
        session.commit()

        repository = AgentEventRepository(session)
        events = repository.list_system_events(
            SystemEventListFilters(
                agent_name="firehose",
                severity=EventSeverity.ERROR,
                since=datetime(2026, 3, 10, 11, 0, tzinfo=timezone.utc),
                until=datetime(2026, 3, 10, 11, 10, tzinfo=timezone.utc),
                limit=10,
            )
        )
        latest_runs = repository.get_latest_run_per_agent()

    assert [event.event_type for event in events] == ["agent_failed"]
    assert [(run.agent_name, run.id) for run in latest_runs] == [("analyst", 3), ("firehose", 2)]


def test_agent_event_repository_lists_pause_states_in_agent_name_order() -> None:
    with _make_session() as session:
        session.add_all(
            [
                AgentPauseState(agent_name="firehose", is_paused=True),
                AgentPauseState(agent_name="analyst", is_paused=False),
                AgentPauseState(agent_name="backfill", is_paused=True),
            ]
        )
        session.commit()

        repository = AgentEventRepository(session)
        pause_states = repository.list_agent_pause_states()

    assert [state.agent_name for state in pause_states] == [
        "analyst",
        "backfill",
        "firehose",
    ]


def test_agent_event_repository_list_events_for_run_excludes_cross_agent_pause_events() -> None:
    with _make_session() as session:
        session.add_all(
            [
                AgentRun(
                    id=1,
                    agent_name="firehose",
                    status=AgentRunStatus.FAILED,
                    started_at=datetime(2026, 3, 10, 11, 0, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 3, 10, 11, 5, tzinfo=timezone.utc),
                    duration_seconds=300.0,
                ),
                AgentRun(
                    id=2,
                    agent_name="backfill",
                    status=AgentRunStatus.COMPLETED,
                    started_at=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 3, 10, 10, 5, tzinfo=timezone.utc),
                    duration_seconds=300.0,
                ),
            ]
        )
        session.add_all(
            [
                SystemEvent(
                    event_type="rate_limit_hit",
                    agent_name="firehose",
                    severity=EventSeverity.ERROR,
                    message="firehose hit the GitHub rate limit.",
                    agent_run_id=1,
                    created_at=datetime(2026, 3, 10, 11, 1, tzinfo=timezone.utc),
                ),
                SystemEvent(
                    event_type="agent_paused",
                    agent_name="firehose",
                    severity=EventSeverity.CRITICAL,
                    message="firehose paused: Wait for rate limit window to expire.",
                    agent_run_id=1,
                    created_at=datetime(2026, 3, 10, 11, 2, tzinfo=timezone.utc),
                ),
                SystemEvent(
                    event_type="agent_paused",
                    agent_name="backfill",
                    severity=EventSeverity.CRITICAL,
                    message="backfill paused: Wait for rate limit window to expire.",
                    agent_run_id=None,
                    created_at=datetime(2026, 3, 10, 11, 2, tzinfo=timezone.utc),
                ),
            ]
        )
        session.commit()

        repository = AgentEventRepository(session)
        run_events = repository.list_events_for_run(1)

    assert [(event.agent_name, event.event_type) for event in run_events] == [
        ("firehose", "rate_limit_hit"),
        ("firehose", "agent_paused"),
    ]

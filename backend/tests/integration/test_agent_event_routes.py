from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_agent_event_service
from app.main import app
from app.models import AgentPauseState, AgentRun, AgentRunStatus, EventSeverity, ResumedBy, SystemEvent
from app.repositories.agent_event_repository import AgentEventRepository
from app.services.agent_event_service import AgentEventService


def _build_service(session: Session) -> AgentEventService:
    return AgentEventService(AgentEventRepository(session))


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_agent_event_service] = lambda: _build_service(db_session)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _seed_agent_events(session: Session) -> None:
    session.add_all(
        [
            AgentRun(
                id=1,
                agent_name="firehose",
                status=AgentRunStatus.COMPLETED,
                started_at=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 3, 10, 10, 4, tzinfo=timezone.utc),
                duration_seconds=240.0,
                items_processed=12,
                items_succeeded=12,
                items_failed=0,
            ),
            AgentRun(
                id=2,
                agent_name="firehose",
                status=AgentRunStatus.FAILED,
                started_at=datetime(2026, 3, 10, 11, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 3, 10, 11, 6, tzinfo=timezone.utc),
                duration_seconds=360.0,
                items_processed=8,
                items_succeeded=5,
                items_failed=3,
                error_summary="firehose rate limited",
                error_context='{"retry_after_seconds": 60}',
            ),
            AgentRun(
                id=3,
                agent_name="analyst",
                status=AgentRunStatus.COMPLETED,
                started_at=datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 3, 10, 9, 3, tzinfo=timezone.utc),
                duration_seconds=180.0,
                items_processed=2,
                items_succeeded=2,
                items_failed=0,
            ),
        ]
    )
    session.add_all(
        [
            SystemEvent(
                id=1,
                event_type="agent_started",
                agent_name="firehose",
                severity=EventSeverity.INFO,
                message="firehose run started.",
                agent_run_id=2,
                created_at=datetime(2026, 3, 10, 11, 0, tzinfo=timezone.utc),
            ),
            SystemEvent(
                id=2,
                event_type="rate_limit_hit",
                agent_name="firehose",
                severity=EventSeverity.WARNING,
                message="firehose hit the GitHub rate limit and backed off.",
                agent_run_id=2,
                context_json='{"retry_after_seconds": 60}',
                created_at=datetime(2026, 3, 10, 11, 5, tzinfo=timezone.utc),
            ),
            SystemEvent(
                id=3,
                event_type="agent_failed",
                agent_name="firehose",
                severity=EventSeverity.ERROR,
                message="firehose rate limited",
                agent_run_id=2,
                created_at=datetime(2026, 3, 10, 11, 6, tzinfo=timezone.utc),
            ),
        ]
    )
    session.commit()


def test_agent_event_routes_expose_filtered_runs_latest_and_detail(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_agent_events(db_session)

    list_response = client.get("/api/v1/agents/runs", params={"agent_name": "firehose"})
    latest_response = client.get("/api/v1/agents/runs/latest")
    detail_response = client.get("/api/v1/agents/runs/2")

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [2, 1]

    assert latest_response.status_code == 200
    latest_payload = latest_response.json()
    assert [entry["agent_name"] for entry in latest_payload["agents"]] == [
        "firehose",
        "backfill",
        "bouncer",
        "analyst",
        "overlord",
        "combiner",
        "obsession",
    ]
    firehose_entry = next(entry for entry in latest_payload["agents"] if entry["agent_name"] == "firehose")
    assert firehose_entry["display_name"] == "Firehose"
    assert firehose_entry["configured_provider"] == "github"
    assert firehose_entry["uses_github_token"] is True
    assert firehose_entry["latest_run"]["provider_name"] is None
    assert firehose_entry["latest_run"]["total_tokens"] is None
    assert firehose_entry["latest_run"]["error_summary"] == "firehose rate limited"

    analyst_entry = next(entry for entry in latest_payload["agents"] if entry["agent_name"] == "analyst")
    assert analyst_entry["configured_provider"] == "heuristic-readme-analysis"
    assert analyst_entry["uses_model"] is False
    assert analyst_entry["latest_run"]["status"] == "completed"

    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["id"] == 2
    assert payload["error_context"] == '{"retry_after_seconds": 60}'
    assert [event["event_type"] for event in payload["events"]] == [
        "agent_started",
        "rate_limit_hit",
        "agent_failed",
    ]


def test_agent_event_routes_filter_system_events_and_return_404_for_missing_runs(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_agent_events(db_session)

    events_response = client.get(
        "/api/v1/events",
        params={
            "agent_name": "firehose",
            "severity": "warning",
            "since": "2026-03-10T11:00:00Z",
            "until": "2026-03-10T11:05:00Z",
        },
    )
    missing_response = client.get("/api/v1/agents/runs/999")

    assert events_response.status_code == 200
    assert events_response.json() == [
        {
            "id": 2,
            "event_type": "rate_limit_hit",
            "agent_name": "firehose",
            "severity": "warning",
            "message": "firehose hit the GitHub rate limit and backed off.",
            "context_json": '{"retry_after_seconds": 60}',
            "agent_run_id": 2,
            "created_at": "2026-03-10T11:05:00Z",
            "failure_classification": None,
            "failure_severity": None,
            "http_status_code": None,
            "retry_after_seconds": None,
            "affected_repository_id": None,
            "upstream_provider": None,
        }
    ]

    assert missing_response.status_code == 404
    assert missing_response.json() == {
        "error": {
            "code": "agent_run_not_found",
            "message": "Agent run 999 was not found.",
            "details": {"run_id": 999},
        }
    }


def test_agent_event_routes_reject_limits_above_supported_maximum(
    client: TestClient,
) -> None:
    runs_response = client.get("/api/v1/agents/runs", params={"limit": 201})
    events_response = client.get("/api/v1/events", params={"limit": 201})

    assert runs_response.status_code == 422
    assert events_response.status_code == 422


def test_pause_state_routes_return_all_and_single_agent_states(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add_all(
        [
            AgentPauseState(
                agent_name="firehose",
                is_paused=True,
                paused_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
                pause_reason="GitHub rate limit",
                resume_condition="Wait for rate-limit window to expire.",
                triggered_by_event_id=5,
            ),
            AgentPauseState(
                agent_name="analyst",
                is_paused=False,
                resumed_at=datetime(2026, 3, 10, 13, 0, tzinfo=timezone.utc),
                resumed_by=ResumedBy.AUTO,
            ),
        ]
    )
    db_session.commit()

    all_response = client.get("/api/v1/agents/pause-state")
    single_response = client.get("/api/v1/agents/firehose/pause-state")
    # bouncer has never been paused — expect synthetic is_paused=False, not 404
    unpaused_response = client.get("/api/v1/agents/bouncer/pause-state")
    # unknown agent names still 404
    unknown_response = client.get("/api/v1/agents/nonexistent/pause-state")

    assert all_response.status_code == 200
    assert len(all_response.json()) == 2
    assert all_response.json()[0]["agent_name"] == "analyst"
    assert all_response.json()[0]["is_paused"] is False
    assert all_response.json()[1]["agent_name"] == "firehose"
    assert all_response.json()[1]["is_paused"] is True
    assert all_response.json()[1]["pause_reason"] == "GitHub rate limit"

    assert single_response.status_code == 200
    assert single_response.json()["agent_name"] == "firehose"
    assert single_response.json()["is_paused"] is True

    assert unpaused_response.status_code == 200
    assert unpaused_response.json()["agent_name"] == "bouncer"
    assert unpaused_response.json()["is_paused"] is False

    assert unknown_response.status_code == 404
    assert unknown_response.json()["error"]["code"] == "agent_not_found"


def test_manual_pause_and_resume_clear_stale_triggering_event_id(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add(
        AgentPauseState(
            agent_name="firehose",
            is_paused=False,
            resumed_at=datetime(2026, 3, 10, 13, 0, tzinfo=timezone.utc),
            resumed_by=ResumedBy.OPERATOR,
            triggered_by_event_id=42,
        )
    )
    db_session.commit()

    pause_response = client.post(
        "/api/v1/agents/firehose/pause",
        json={
            "pause_reason": "Operator inspection",
            "resume_condition": "Resume manually after inspection",
        },
    )
    assert pause_response.status_code == 200
    assert pause_response.json()["is_paused"] is True
    assert pause_response.json()["triggered_by_event_id"] is None

    resume_response = client.post("/api/v1/agents/firehose/resume")
    assert resume_response.status_code == 200
    assert resume_response.json()["is_paused"] is False
    assert resume_response.json()["triggered_by_event_id"] is None

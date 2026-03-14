from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_agent_event_service
from app.main import app
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
def client(db_session: Session):
    def override_service():
        return _build_service(db_session)

    app.dependency_overrides[get_agent_event_service] = override_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_incidents_empty(client):
    response = client.get("/api/v1/incidents")
    assert response.status_code == 200
    assert response.json() == []


def test_list_incidents_with_filters(client, db_session):
    from app.models import SystemEvent, EventSeverity, FailureClassification, FailureSeverity
    from datetime import datetime, timezone

    # Create events with different attributes
    event1 = SystemEvent(
        event_type="rate_limit_hit",
        agent_name="firehose",
        severity=EventSeverity.CRITICAL,
        message="Rate limit",
        failure_classification=FailureClassification.RATE_LIMITED,
        failure_severity=FailureSeverity.CRITICAL,
    )
    event2 = SystemEvent(
        event_type="agent.failure",
        agent_name="backfill",
        severity=EventSeverity.ERROR,
        message="Blocking failure",
        failure_classification=FailureClassification.BLOCKING,
        failure_severity=FailureSeverity.ERROR,
    )
    db_session.add_all([event1, event2])
    db_session.commit()

    # Test agent_name filter
    response = client.get("/api/v1/incidents?agent_name=firehose")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["agent_name"] == "firehose"

    # Test severity filter
    response = client.get("/api/v1/incidents?severity=critical")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["severity"] == "critical"

    # Test classification filter
    response = client.get("/api/v1/incidents?classification=blocking")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["failure_classification"] == "blocking"


def test_get_incident_not_found(client):
    response = client.get("/api/v1/incidents/99999")
    assert response.status_code == 404
    assert "not found" in response.json()["error"]["message"].lower()


def test_list_incidents_with_data(client, db_session):
    from app.models import SystemEvent, EventSeverity, FailureClassification, FailureSeverity, AgentRun, AgentRunStatus, RepositoryIntake
    from datetime import datetime, timezone

    # Create repository
    repo = RepositoryIntake(
        github_repository_id=123,
        owner_login="test",
        repository_name="repo",
        full_name="test/repo",
        stargazers_count=10,
        forks_count=5,
    )
    db_session.add(repo)
    db_session.commit()

    # Create run
    run = AgentRun(
        agent_name="firehose",
        status=AgentRunStatus.FAILED,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    # Create incident event
    event = SystemEvent(
        event_type="agent.failure",
        agent_name="firehose",
        severity=EventSeverity.CRITICAL,
        message="Rate limit exceeded",
        failure_classification=FailureClassification.RATE_LIMITED,
        failure_severity=FailureSeverity.CRITICAL,
        affected_repository_id=123,
        agent_run_id=run.id,
        context_json='{"full_name": "test/repo"}',
    )
    db_session.add(event)
    db_session.commit()

    response = client.get("/api/v1/incidents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["agent_name"] == "firehose"
    assert data[0]["repository_full_name"] == "test/repo"


def test_get_incident_with_enrichment(client, db_session):
    from app.models import SystemEvent, EventSeverity, FailureClassification, AgentRun, AgentRunStatus, RepositoryIntake
    from datetime import datetime, timezone

    repo = RepositoryIntake(
        github_repository_id=456,
        owner_login="owner",
        repository_name="project",
        full_name="owner/project",
        stargazers_count=100,
        forks_count=20,
    )
    db_session.add(repo)
    db_session.commit()

    run = AgentRun(
        agent_name="analyst",
        status=AgentRunStatus.FAILED,
        started_at=datetime.now(timezone.utc),
        error_summary="Analysis failed",
    )
    db_session.add(run)
    db_session.commit()

    event = SystemEvent(
        event_type="agent.failure",
        agent_name="analyst",
        severity=EventSeverity.ERROR,
        message="Failed to analyze",
        failure_classification=FailureClassification.BLOCKING,
        affected_repository_id=456,
        agent_run_id=run.id,
        context_json='{"mode": "analysis", "page": 1}',
    )
    db_session.add(event)
    db_session.commit()

    response = client.get(f"/api/v1/incidents/{event.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["repository_full_name"] == "owner/project"
    assert data["checkpoint_context"]["mode"] == "analysis"
    assert data["run_error_summary"] == "Analysis failed"


def test_incident_with_invalid_context_json(client, db_session):
    from app.models import SystemEvent, EventSeverity

    event = SystemEvent(
        event_type="agent.failure",
        agent_name="bouncer",
        severity=EventSeverity.ERROR,
        message="Invalid context",
        context_json='{"invalid": json}',  # Malformed JSON
    )
    db_session.add(event)
    db_session.commit()

    response = client.get(f"/api/v1/incidents/{event.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["checkpoint_context"] is None


def test_incident_with_backfill_checkpoint(client, db_session):
    from app.models import SystemEvent, EventSeverity, FailureClassification

    event = SystemEvent(
        event_type="rate_limit_hit",
        agent_name="backfill",
        severity=EventSeverity.CRITICAL,
        message="Backfill rate limited",
        failure_classification=FailureClassification.RATE_LIMITED,
        context_json='{"window_start_date": "2024-01-01T00:00:00", "created_before_boundary": "2024-01-31T23:59:59", "page": 1}',
    )
    db_session.add(event)
    db_session.commit()

    response = client.get(f"/api/v1/incidents/{event.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["checkpoint_context"] is not None
    assert data["checkpoint_context"]["window_start"] == "2024-01-01T00:00:00"
    assert data["checkpoint_context"]["window_end"] == "2024-01-31T23:59:59"


def test_incident_next_action_derivation(client, db_session):
    from app.models import SystemEvent, EventSeverity, FailureClassification, FailureSeverity

    event = SystemEvent(
        event_type="rate_limit_hit",
        agent_name="firehose",
        severity=EventSeverity.CRITICAL,
        message="Rate limited",
        failure_classification=FailureClassification.RATE_LIMITED,
        failure_severity=FailureSeverity.CRITICAL,
        retry_after_seconds=3600,
        context_json='{"is_paused": true, "pause_reason": "Rate limit", "resume_condition": "Manual resume after rate limit window"}',
    )
    db_session.add(event)
    db_session.commit()

    response = client.get(f"/api/v1/incidents/{event.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["next_action"] is not None
    assert "paused" in data["next_action"].lower() or "resume" in data["next_action"].lower()


def test_incident_with_run_error_context(client, db_session):
    from app.models import SystemEvent, EventSeverity, AgentRun, AgentRunStatus
    from datetime import datetime, timezone

    run = AgentRun(
        agent_name="analyst",
        status=AgentRunStatus.FAILED,
        started_at=datetime.now(timezone.utc),
        error_summary="Analysis failed",
        error_context='{"mode": "deep_analysis", "checkpoint": "phase_2"}',
    )
    db_session.add(run)
    db_session.commit()

    event = SystemEvent(
        event_type="agent.failure",
        agent_name="analyst",
        severity=EventSeverity.ERROR,
        message="Failed",
        agent_run_id=run.id,
    )
    db_session.add(event)
    db_session.commit()

    response = client.get(f"/api/v1/incidents/{event.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["run_error_context"] is not None
    assert "mode" in data["run_error_context"]


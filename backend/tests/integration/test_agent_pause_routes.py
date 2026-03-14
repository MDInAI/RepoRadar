"""Integration tests for agent pause state API endpoints."""
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_agent_event_service
from app.main import app
from app.models import AgentPauseState, FirehoseProgress, BackfillProgress, RepositoryIntake
from app.repositories.agent_event_repository import AgentEventRepository
from app.services.agent_event_service import AgentEventService


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
    app.dependency_overrides[get_agent_event_service] = lambda: AgentEventService(
        AgentEventRepository(db_session)
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_list_agent_pause_states_empty(client: TestClient) -> None:
    """GET /api/v1/agents/pause-state returns empty list when no pause states exist."""
    response = client.get("/api/v1/agents/pause-state")
    assert response.status_code == 200
    assert response.json() == []


def test_list_agent_pause_states_returns_all_states(
    client: TestClient, db_session: Session
) -> None:
    """GET /api/v1/agents/pause-state returns all pause states."""
    db_session.add(
        AgentPauseState(
            agent_name="firehose",
            is_paused=True,
            paused_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
            pause_reason="Rate limit",
            resume_condition="Wait for rate limit to expire",
        )
    )
    db_session.add(
        AgentPauseState(
            agent_name="analyst",
            is_paused=False,
        )
    )
    db_session.commit()

    response = client.get("/api/v1/agents/pause-state")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["agent_name"] == "analyst"
    assert data[0]["is_paused"] is False
    assert data[1]["agent_name"] == "firehose"
    assert data[1]["is_paused"] is True


def test_get_agent_pause_state_returns_state(
    client: TestClient, db_session: Session
) -> None:
    """GET /api/v1/agents/{agent_name}/pause-state returns specific agent state."""
    db_session.add(
        AgentPauseState(
            agent_name="bouncer",
            is_paused=True,
            paused_at=datetime(2026, 3, 10, 14, 30, tzinfo=timezone.utc),
            pause_reason="Blocking failure",
            resume_condition="Operator review required",
        )
    )
    db_session.commit()

    response = client.get("/api/v1/agents/bouncer/pause-state")
    assert response.status_code == 200
    data = response.json()
    assert data["agent_name"] == "bouncer"
    assert data["is_paused"] is True
    assert data["pause_reason"] == "Blocking failure"


def test_get_agent_pause_state_returns_404_when_not_found(
    client: TestClient,
) -> None:
    """GET /api/v1/agents/{agent_name}/pause-state returns 404 when agent not found."""
    response = client.get("/api/v1/agents/nonexistent/pause-state")
    assert response.status_code == 404


def test_resume_agent_success_firehose(client: TestClient, db_session: Session) -> None:
    """POST /api/v1/agents/{agent_name}/resume successfully resumes paused firehose agent."""
    db_session.add(
        AgentPauseState(
            agent_name="firehose",
            is_paused=True,
            paused_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
            pause_reason="Rate limit",
        )
    )
    db_session.add(
        FirehoseProgress(
            active_mode="trending",
            next_page=1,
            resume_required=True,
            new_anchor_date=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
            trending_anchor_date=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
            run_started_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    response = client.post("/api/v1/agents/firehose/resume")
    assert response.status_code == 200
    data = response.json()
    assert data["agent_name"] == "firehose"
    assert data["is_paused"] is False
    assert data["resumed_by"] == "operator"


def test_resume_agent_success_bouncer(client: TestClient, db_session: Session) -> None:
    """POST /api/v1/agents/{agent_name}/resume successfully resumes paused bouncer agent."""
    db_session.add(
        AgentPauseState(
            agent_name="bouncer",
            is_paused=True,
            paused_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
        )
    )
    db_session.add(
        RepositoryIntake(
            github_repository_id=123,
            owner_login="test",
            repository_name="repo",
            full_name="test/repo",
            queue_status="pending",
            triage_status="pending",
        )
    )
    db_session.commit()

    response = client.post("/api/v1/agents/bouncer/resume")
    assert response.status_code == 200
    data = response.json()
    assert data["is_paused"] is False


def test_resume_agent_rejects_unknown_agent(client: TestClient) -> None:
    """POST /api/v1/agents/{agent_name}/resume returns 404 for unknown agent."""
    response = client.post("/api/v1/agents/unknown/resume")
    assert response.status_code == 404


def test_resume_agent_rejects_unpaused_agent(client: TestClient, db_session: Session) -> None:
    """POST /api/v1/agents/{agent_name}/resume returns 409 for unpaused agent."""
    db_session.add(AgentPauseState(agent_name="firehose", is_paused=False))
    db_session.commit()

    response = client.post("/api/v1/agents/firehose/resume")
    assert response.status_code == 409


def test_resume_agent_rejects_missing_checkpoint(client: TestClient, db_session: Session) -> None:
    """POST /api/v1/agents/{agent_name}/resume returns 422 when checkpoint missing."""
    db_session.add(
        AgentPauseState(
            agent_name="firehose",
            is_paused=True,
            paused_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    response = client.post("/api/v1/agents/firehose/resume")
    assert response.status_code == 422


def test_pause_agent_success(client: TestClient, db_session: Session) -> None:
    """POST /api/v1/agents/{agent_name}/pause successfully pauses agent with metadata."""
    response = client.post(
        "/api/v1/agents/firehose/pause",
        json={
            "pause_reason": "Rate limit detected",
            "resume_condition": "Wait 1 hour for reset"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["agent_name"] == "firehose"
    assert data["is_paused"] is True
    assert data["pause_reason"] == "Rate limit detected"
    assert data["resume_condition"] == "Wait 1 hour for reset"
    assert data["paused_at"] is not None

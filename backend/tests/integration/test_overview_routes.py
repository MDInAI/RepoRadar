from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_db_session
from app.main import app
from app.models import (
    AgentPauseState,
    AgentRun,
    AgentRunStatus,
    RepositoryAnalysisStatus,
    RepositoryDiscoverySource,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
    SystemEvent,
    FailureClassification,
    FailureSeverity,
)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    db_session = Session(engine)
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    def override_get_db_session():
        yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_get_overview_summary_empty(client: TestClient, session: Session):
    response = client.get("/api/v1/overview/summary")
    assert response.status_code == 200
    data = response.json()

    assert data["ingestion"]["total_repositories"] == 0
    assert data["ingestion"]["pending_intake"] == 0
    assert data["triage"]["pending"] == 0
    assert data["analysis"]["completed"] == 0
    assert data["backlog"]["queue_pending"] == 0
    assert data["backlog"]["triage_pending"] == 0
    assert data["backlog"]["analysis_pending"] == 0
    assert len(data["agents"]) == 7
    assert data["failures"]["total_failures"] == 0
    assert data["token_usage"]["total_tokens_24h"] == 0


def test_get_overview_summary_with_data(client: TestClient, session: Session):
    repo1 = RepositoryIntake(
        github_repository_id=1,
        owner_login="owner1",
        repository_name="repo1",
        full_name="owner1/repo1",
        discovery_source=RepositoryDiscoverySource.FIREHOSE,
        firehose_discovery_mode="new",
        queue_status=RepositoryQueueStatus.COMPLETED,
        triage_status=RepositoryTriageStatus.ACCEPTED,
        analysis_status=RepositoryAnalysisStatus.COMPLETED,
    )
    repo2 = RepositoryIntake(
        github_repository_id=2,
        owner_login="owner2",
        repository_name="repo2",
        full_name="owner2/repo2",
        discovery_source=RepositoryDiscoverySource.BACKFILL,
        queue_status=RepositoryQueueStatus.PENDING,
        triage_status=RepositoryTriageStatus.PENDING,
        analysis_status=RepositoryAnalysisStatus.PENDING,
    )
    session.add(repo1)
    session.add(repo2)

    run = AgentRun(
        agent_name="firehose",
        status=AgentRunStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)

    pause_state = AgentPauseState(
        agent_name="bouncer",
        is_paused=True,
        paused_at=datetime.now(timezone.utc),
    )
    session.add(pause_state)

    event = SystemEvent(
        event_type="failure",
        agent_name="analyst",
        message="Test failure",
        failure_classification=FailureClassification.BLOCKING,
        failure_severity=FailureSeverity.CRITICAL,
    )
    session.add(event)

    session.commit()

    response = client.get("/api/v1/overview/summary")
    assert response.status_code == 200
    data = response.json()

    assert data["ingestion"]["total_repositories"] == 2
    assert data["ingestion"]["pending_intake"] == 1
    assert data["ingestion"]["firehose_discovered"] == 1
    assert data["ingestion"]["backfill_discovered"] == 1
    assert data["ingestion"]["discovered_last_24h"] == 2
    assert data["ingestion"]["firehose_discovered_last_24h"] == 1
    assert data["ingestion"]["backfill_discovered_last_24h"] == 1

    assert data["triage"]["pending"] == 1
    assert data["triage"]["accepted"] == 1
    assert data["triage"]["rejected"] == 0

    assert data["analysis"]["pending"] == 1
    assert data["analysis"]["completed"] == 1

    assert data["backlog"]["queue_pending"] == 1
    assert data["backlog"]["queue_completed"] == 1
    assert data["backlog"]["triage_pending"] == 1
    assert data["backlog"]["triage_accepted"] == 1
    assert data["backlog"]["analysis_pending"] == 1
    assert data["backlog"]["analysis_completed"] == 1

    assert len(data["agents"]) == 7
    firehose_agent = next(a for a in data["agents"] if a["agent_name"] == "firehose")
    assert firehose_agent["display_name"] == "Firehose"
    assert firehose_agent["uses_github_token"] is True
    assert firehose_agent["status"] == "completed"
    assert firehose_agent["is_paused"] is False

    bouncer_agent = next(a for a in data["agents"] if a["agent_name"] == "bouncer")
    assert bouncer_agent["is_paused"] is True

    assert data["failures"]["total_failures"] == 1
    assert data["failures"]["critical_failures"] == 1
    assert data["failures"]["blocking_failures"] == 1
    assert data["token_usage"]["total_tokens_24h"] == 0

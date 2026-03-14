import time
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import (
    AgentRun,
    AgentRunStatus,
    RepositoryAnalysisStatus,
    RepositoryDiscoverySource,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
    SystemEvent,
)
from app.api.deps import get_db_session
from app.main import app


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


def test_overview_summary_performance_with_10k_repos(client: TestClient, session: Session):
    """Verify summary loads within 1.0s with 10,000+ repositories."""
    repos = [
        RepositoryIntake(
            github_repository_id=i,
            owner_login=f"owner{i}",
            repository_name=f"repo{i}",
            full_name=f"owner{i}/repo{i}",
            discovery_source=(
                RepositoryDiscoverySource.FIREHOSE if i % 2 == 0 else RepositoryDiscoverySource.BACKFILL
            ),
            firehose_discovery_mode="new" if i % 2 == 0 else None,
            queue_status=RepositoryQueueStatus.COMPLETED,
            triage_status=RepositoryTriageStatus.ACCEPTED,
            analysis_status=RepositoryAnalysisStatus.COMPLETED,
        )
        for i in range(10000)
    ]
    session.add_all(repos)

    agent_runs = [
        AgentRun(
            agent_name="firehose",
            status=AgentRunStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        ),
        AgentRun(
            agent_name="bouncer",
            status=AgentRunStatus.FAILED,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        ),
    ]
    session.add_all(agent_runs)

    events = [
        SystemEvent(
            event_type="rate_limit",
            agent_name="analyst",
            severity="error",
            message="Rate limited",
            failure_classification="rate_limited",
            failure_severity="error",
        )
    ]
    session.add_all(events)
    session.commit()

    start = time.time()
    response = client.get("/api/v1/overview/summary")
    duration = time.time() - start

    assert response.status_code == 200
    assert duration < 1.0, f"Summary took {duration:.2f}s, expected < 1.0s"

    data = response.json()
    assert data["ingestion"]["total_repositories"] == 10000

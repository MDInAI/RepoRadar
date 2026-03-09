from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.routes.repositories import get_repository_exploration_service
from app.main import app
from app.models import (
    RepositoryAnalysisFailureCode,
    RepositoryAnalysisStatus,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
)
from app.repositories.repository_exploration_repository import RepositoryExplorationRepository
from app.services.repository_exploration_service import RepositoryExplorationService


def _build_service(session: Session) -> RepositoryExplorationService:
    return RepositoryExplorationService(RepositoryExplorationRepository(session))


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
def api_client(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_repository_exploration_service] = lambda: _build_service(
        db_session
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _seed_backlog(session: Session) -> None:
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            RepositoryIntake(
                github_repository_id=701,
                source_provider="github",
                owner_login="alpha",
                repository_name="pending-repo",
                full_name="alpha/pending-repo",
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                firehose_discovery_mode=RepositoryFirehoseMode.NEW,
                queue_status=RepositoryQueueStatus.PENDING,
                triage_status=RepositoryTriageStatus.PENDING,
                analysis_status=RepositoryAnalysisStatus.PENDING,
                stargazers_count=11,
                forks_count=1,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
            ),
            RepositoryIntake(
                github_repository_id=702,
                source_provider="github",
                owner_login="beta",
                repository_name="queue-failed-repo",
                full_name="beta/queue-failed-repo",
                discovery_source=RepositoryDiscoverySource.BACKFILL,
                queue_status=RepositoryQueueStatus.FAILED,
                triage_status=RepositoryTriageStatus.REJECTED,
                analysis_status=RepositoryAnalysisStatus.PENDING,
                stargazers_count=12,
                forks_count=2,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
                last_failed_at=now,
            ),
            RepositoryIntake(
                github_repository_id=703,
                source_provider="github",
                owner_login="gamma",
                repository_name="analysis-failed-repo",
                full_name="gamma/analysis-failed-repo",
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                firehose_discovery_mode=RepositoryFirehoseMode.TRENDING,
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.FAILED,
                stargazers_count=13,
                forks_count=3,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
                processing_started_at=now.replace(hour=11, minute=45),
                processing_completed_at=now.replace(hour=11, minute=55),
                last_failed_at=now.replace(hour=11, minute=57),
                triaged_at=now,
                analysis_started_at=now,
                analysis_completed_at=now,
                analysis_last_failed_at=now,
                analysis_failure_code=RepositoryAnalysisFailureCode.RATE_LIMITED,
                analysis_failure_message="Gateway rate limit while analyzing repository.",
            ),
            RepositoryIntake(
                github_repository_id=704,
                source_provider="github",
                owner_login="delta",
                repository_name="completed-repo",
                full_name="delta/completed-repo",
                discovery_source=RepositoryDiscoverySource.BACKFILL,
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.COMPLETED,
                stargazers_count=14,
                forks_count=4,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
                processing_started_at=now.replace(hour=11, minute=35),
                processing_completed_at=now.replace(hour=11, minute=50),
                analysis_started_at=now,
                analysis_completed_at=now,
                triaged_at=now,
            ),
        ]
    )
    session.commit()


def test_repository_backlog_summary_route_returns_expected_json(
    api_client: TestClient,
    db_session: Session,
) -> None:
    _seed_backlog(db_session)

    response = api_client.get("/api/v1/repositories/backlog/summary")

    assert response.status_code == 200
    assert response.json() == {
        "queue": {"pending": 1, "in_progress": 0, "completed": 2, "failed": 1},
        "triage": {"pending": 1, "accepted": 2, "rejected": 1},
        "analysis": {"pending": 2, "in_progress": 0, "completed": 1, "failed": 1},
    }


def test_repository_catalog_route_supports_backlog_status_filters(
    api_client: TestClient,
    db_session: Session,
) -> None:
    _seed_backlog(db_session)

    queue_response = api_client.get(
        "/api/v1/repositories",
        params={"queue_status": "pending"},
    )
    assert queue_response.status_code == 200
    assert [item["github_repository_id"] for item in queue_response.json()["items"]] == [701]

    failures_response = api_client.get(
        "/api/v1/repositories",
        params={"has_failures": "true"},
    )
    assert failures_response.status_code == 200
    payload = failures_response.json()

    assert [item["github_repository_id"] for item in payload["items"]] == [703, 702]
    assert payload["items"][0]["analysis_failure_code"] == "rate_limited"
    assert payload["items"][0]["analysis_failure_message"] == (
        "Gateway rate limit while analyzing repository."
    )
    assert payload["items"][0]["processing_started_at"] == "2026-03-09T12:00:00Z"
    assert payload["items"][0]["processing_completed_at"] == "2026-03-09T12:00:00Z"
    assert payload["items"][0]["last_failed_at"] == "2026-03-09T12:00:00Z"
    assert payload["items"][1]["last_failed_at"] == "2026-03-09T12:00:00Z"

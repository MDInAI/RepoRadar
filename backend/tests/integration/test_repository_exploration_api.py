from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.routes.repositories import get_repository_exploration_service
from app.main import app
from app.models import (
    RepositoryAnalysisResult,
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryDiscoverySource,
    RepositoryIntake,
    RepositoryMonetizationPotential,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
)
from app.repositories.repository_exploration_repository import RepositoryExplorationRepository
from app.services.repository_exploration_service import RepositoryExplorationService


def _build_repository_exploration_service(session: Session) -> RepositoryExplorationService:
    return RepositoryExplorationService(RepositoryExplorationRepository(session))


@contextmanager
def override_repository_exploration_service(service: object) -> Iterator[None]:
    app.dependency_overrides[get_repository_exploration_service] = lambda: service
    try:
        yield
    finally:
        app.dependency_overrides.clear()


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
    service = _build_repository_exploration_service(db_session)
    with override_repository_exploration_service(service):
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture
def base_repository(db_session: Session) -> RepositoryIntake:
    repo = RepositoryIntake(
        github_repository_id=888,
        source_provider="github",
        owner_login="testowner",
        repository_name="testrepo",
        full_name="testowner/testrepo",
        discovery_source=RepositoryDiscoverySource.BACKFILL,
        queue_status=RepositoryQueueStatus.COMPLETED,
        triage_status=RepositoryTriageStatus.ACCEPTED,
        stargazers_count=100,
        forks_count=20,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


def test_get_repository_exploration_success(
    client: TestClient,
    db_session: Session,
    base_repository: RepositoryIntake,
) -> None:
    # Add artifacts and analysis
    artifact = RepositoryArtifact(
        github_repository_id=base_repository.github_repository_id,
        artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
        runtime_relative_path="readmes/888.md",
        content_sha256="fakehash",
        byte_size=1024,
        content_type="text/markdown",
        source_kind="github_readme",
        generated_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add(artifact)

    analysis = RepositoryAnalysisResult(
        github_repository_id=base_repository.github_repository_id,
        monetization_potential=RepositoryMonetizationPotential.HIGH,
        pros=["Great tech"],
        analyzed_at=datetime(2026, 3, 9, 12, 5, tzinfo=timezone.utc),
    )
    db_session.add(analysis)
    db_session.commit()

    response = client.get(f"/api/v1/repositories/{base_repository.github_repository_id}")
    assert response.status_code == 200
    data = response.json()

    assert data["github_repository_id"] == 888
    assert data["full_name"] == "testowner/testrepo"
    assert data["triage_status"] == "accepted"
    assert data["stargazers_count"] == 100
    assert data["has_readme_artifact"] is True
    assert data["has_analysis_artifact"] is False
    assert len(data["artifacts"]) == 1
    assert data["artifacts"][0]["artifact_kind"] == "readme_snapshot"
    assert data["analysis_summary"]["monetization_potential"] == "high"
    assert "Great tech" in data["analysis_summary"]["pros"]


def test_get_repository_exploration_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/repositories/999999999")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "repository_not_found"
    assert "999999999" in data["error"]["message"]
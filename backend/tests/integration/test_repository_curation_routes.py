from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_repository_curation_service, get_repository_exploration_service
from app.main import app
from app.models import (
    RepositoryAnalysisResult,
    RepositoryAnalysisStatus,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryMonetizationPotential,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
)
from app.repositories.repository_curation_repository import RepositoryCurationRepository
from app.repositories.repository_exploration_repository import RepositoryExplorationRepository
from app.services.repository_curation_service import RepositoryCurationService
from app.services.repository_exploration_service import RepositoryExplorationService


def _build_repository_curation_service(session: Session) -> RepositoryCurationService:
    return RepositoryCurationService(RepositoryCurationRepository(session))


def _build_repository_exploration_service(session: Session) -> RepositoryExplorationService:
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
def client(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_repository_curation_service] = lambda: _build_repository_curation_service(
        db_session
    )
    app.dependency_overrides[
        get_repository_exploration_service
    ] = lambda: _build_repository_exploration_service(db_session)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _seed_catalog(db_session: Session) -> None:
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    db_session.add_all(
        [
            RepositoryIntake(
                github_repository_id=701,
                source_provider="github",
                owner_login="alpha",
                repository_name="growth-engine",
                full_name="alpha/growth-engine",
                repository_description="Growth workflows for operators",
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                firehose_discovery_mode=RepositoryFirehoseMode.TRENDING,
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.COMPLETED,
                stargazers_count=900,
                forks_count=90,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
                triaged_at=now,
                analysis_started_at=now,
                analysis_completed_at=now,
                analysis_last_attempted_at=now,
                pushed_at=now,
            ),
            RepositoryIntake(
                github_repository_id=702,
                source_provider="github",
                owner_login="beta",
                repository_name="sales-hub",
                full_name="beta/sales-hub",
                repository_description="Sales automation catalog",
                discovery_source=RepositoryDiscoverySource.BACKFILL,
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.COMPLETED,
                stargazers_count=120,
                forks_count=12,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
                triaged_at=now,
                analysis_started_at=now,
                analysis_completed_at=now,
                analysis_last_attempted_at=now,
                pushed_at=now,
            ),
        ]
    )
    db_session.add_all(
        [
            RepositoryAnalysisResult(
                github_repository_id=701,
                monetization_potential=RepositoryMonetizationPotential.HIGH,
                pros=["Strong ICP"],
                analyzed_at=now,
            ),
            RepositoryAnalysisResult(
                github_repository_id=702,
                monetization_potential=RepositoryMonetizationPotential.MEDIUM,
                pros=["Broad market"],
                analyzed_at=now,
            ),
        ]
    )
    db_session.commit()


def test_repository_curation_routes_support_full_crud_lifecycle(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_catalog(db_session)

    initial = client.get("/api/v1/repositories/701/curation")
    assert initial.status_code == 200
    assert initial.json() == {
        "is_starred": False,
        "starred_at": None,
        "user_tags": [],
    }

    starred = client.put("/api/v1/repositories/701/star", json={"starred": True})
    assert starred.status_code == 200
    assert starred.json()["is_starred"] is True
    assert starred.json()["starred_at"] is not None

    created_tag = client.post("/api/v1/repositories/701/tags", json={"tag_label": "workflow"})
    assert created_tag.status_code == 201
    assert created_tag.json()["tag_label"] == "workflow"

    duplicate_tag = client.post("/api/v1/repositories/701/tags", json={"tag_label": "workflow"})
    assert duplicate_tag.status_code == 409
    assert duplicate_tag.json()["error"]["code"] == "repository_user_tag_conflict"

    refreshed = client.get("/api/v1/repositories/701/curation")
    assert refreshed.status_code == 200
    assert refreshed.json()["is_starred"] is True
    assert refreshed.json()["user_tags"] == ["workflow"]

    removed = client.delete(f"/api/v1/repositories/701/tags/{quote('workflow', safe='')}")
    assert removed.status_code == 204

    unstarred = client.put("/api/v1/repositories/701/star", json={"starred": False})
    assert unstarred.status_code == 200
    assert unstarred.json() == {
        "is_starred": False,
        "starred_at": None,
        "user_tags": [],
    }


def test_repository_catalog_supports_starred_only_filter(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_catalog(db_session)
    client.put("/api/v1/repositories/701/star", json={"starred": True})

    response = client.get("/api/v1/repositories?starred_only=true")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert [item["github_repository_id"] for item in data["items"]] == [701]
    assert data["items"][0]["is_starred"] is True


def test_repository_catalog_supports_user_tag_filter(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_catalog(db_session)
    client.post("/api/v1/repositories/701/tags", json={"tag_label": "workflow"})
    client.post("/api/v1/repositories/702/tags", json={"tag_label": "sales"})

    response = client.get("/api/v1/repositories?user_tag=workflow")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert [item["github_repository_id"] for item in data["items"]] == [701]
    assert data["items"][0]["user_tags"] == ["workflow"]

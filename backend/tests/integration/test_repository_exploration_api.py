from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.routes.repositories import get_repository_exploration_service
from app.core.config import settings
from app.main import app
from app.models import (
    RepositoryAnalysisResult,
    RepositoryAnalysisStatus,
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryMonetizationPotential,
    RepositoryQueueStatus,
    RepositoryTriageExplanation,
    RepositoryTriageExplanationKind,
    RepositoryTriageStatus,
)
from app.repositories.repository_exploration_repository import RepositoryExplorationRepository
from app.services.repository_exploration_service import RepositoryExplorationService


def _build_repository_exploration_service(session: Session) -> RepositoryExplorationService:
    return RepositoryExplorationService(
        RepositoryExplorationRepository(session),
        runtime_dir=settings.AGENTIC_RUNTIME_DIR,
    )


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
    app.dependency_overrides[get_repository_exploration_service] = (
        lambda: _build_repository_exploration_service(db_session)
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


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
                triage_status=RepositoryTriageStatus.REJECTED,
                analysis_status=RepositoryAnalysisStatus.FAILED,
                stargazers_count=120,
                forks_count=12,
                discovered_at=now.replace(day=8),
                queue_created_at=now.replace(day=8),
                status_updated_at=now.replace(day=8),
                triaged_at=now.replace(day=8),
                pushed_at=now.replace(day=8),
            ),
        ]
    )
    db_session.add(
        RepositoryAnalysisResult(
            github_repository_id=701,
            monetization_potential=RepositoryMonetizationPotential.HIGH,
            pros=["Strong ICP"],
            analyzed_at=now,
        )
    )
    db_session.add(
        RepositoryArtifact(
            github_repository_id=701,
            artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
            runtime_relative_path="readmes/701.md",
            content_sha256="a" * 64,
            byte_size=1024,
            content_type="text/markdown",
            source_kind="github_readme",
            generated_at=now,
        )
    )
    db_session.commit()


def test_get_repository_exploration_success(
    client: TestClient,
    db_session: Session,
    base_repository: RepositoryIntake,
    tmp_path: Path,
) -> None:
    # Add artifacts and analysis
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    artifact = RepositoryArtifact(
        github_repository_id=base_repository.github_repository_id,
        artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
        runtime_relative_path="readmes/888.md",
        content_sha256="fakehash",
        byte_size=1024,
        content_type="text/markdown",
        source_kind="github_readme",
        provenance_metadata={
            "normalization_version": "story-3.4-v1",
            "raw_character_count": 2200,
            "normalized_character_count": 840,
            "removed_line_count": 12,
        },
        generated_at=now,
    )
    db_session.add(artifact)
    db_session.add(
        RepositoryArtifact(
            github_repository_id=base_repository.github_repository_id,
            artifact_kind=RepositoryArtifactKind.ANALYSIS_RESULT,
            runtime_relative_path="analyses/888.json",
            content_sha256="analysishash",
            byte_size=2048,
            content_type="application/json",
            source_kind="repository_analysis",
            provenance_metadata={"analysis_provider": "StaticAnalysisProvider"},
            generated_at=now,
        )
    )

    analysis = RepositoryAnalysisResult(
        github_repository_id=base_repository.github_repository_id,
        monetization_potential=RepositoryMonetizationPotential.HIGH,
        pros=["Great tech"],
        cons=["Pricing unknown"],
        missing_feature_signals=["Missing SSO"],
        source_metadata={
            "readme_artifact_path": "readmes/888.md",
            "analysis_artifact_path": "analyses/888.json",
            "analysis_provider": "StaticAnalysisProvider",
            "normalization_version": "story-3.4-v1",
            "raw_character_count": 2200,
            "normalized_character_count": 840,
            "removed_line_count": 12,
        },
        analyzed_at=datetime(2026, 3, 9, 12, 5, tzinfo=timezone.utc),
    )
    db_session.add(analysis)
    base_repository.queue_created_at = now
    base_repository.triaged_at = now
    db_session.add(base_repository)
    db_session.add(
        RepositoryTriageExplanation(
            github_repository_id=base_repository.github_repository_id,
            explanation_kind=RepositoryTriageExplanationKind.INCLUDE_RULE,
            explanation_summary="Accepted because workflow automation matched the include set.",
            matched_include_rules=["workflow", "automation"],
            matched_exclude_rules=[],
            explained_at=now,
        )
    )
    db_session.commit()
    runtime_dir = tmp_path / "runtime"
    (runtime_dir / "readmes").mkdir(parents=True)
    (runtime_dir / "analyses").mkdir(parents=True)
    (runtime_dir / "readmes" / "888.md").write_text(
        "# Test Repo\n\nWorkflow automation with analytics.",
        encoding="utf-8",
    )
    (runtime_dir / "analyses" / "888.json").write_text(
        json.dumps(
            {
                "schema_version": "story-3.4-v1",
                "github_repository_id": 888,
                "analysis_provider": "StaticAnalysisProvider",
                "analysis": {
                    "monetization_potential": "high",
                    "pros": ["Great tech"],
                    "cons": ["Pricing unknown"],
                    "missing_feature_signals": ["Missing SSO"],
                },
            }
        ),
        encoding="utf-8",
    )
    original_runtime_dir = settings.AGENTIC_RUNTIME_DIR
    settings.AGENTIC_RUNTIME_DIR = runtime_dir

    try:
        response = client.get(f"/api/v1/repositories/{base_repository.github_repository_id}")
    finally:
        settings.AGENTIC_RUNTIME_DIR = original_runtime_dir

    assert response.status_code == 200
    data = response.json()

    assert data["github_repository_id"] == 888
    assert data["full_name"] == "testowner/testrepo"
    assert data["owner_login"] == "testowner"
    assert data["repository_name"] == "testrepo"
    assert data["intake_status"] == "completed"
    assert data["triage_status"] == "accepted"
    assert data["stargazers_count"] == 100
    assert data["has_readme_artifact"] is True
    assert data["has_analysis_artifact"] is True
    assert len(data["artifacts"]) == 2
    assert data["analysis_summary"]["monetization_potential"] == "high"
    assert "Great tech" in data["analysis_summary"]["pros"]
    assert data["triage"]["explanation"]["kind"] == "include_rule"
    assert data["triage"]["explanation"]["matched_include_rules"] == ["workflow", "automation"]
    assert data["readme_snapshot"]["content"] == "# Test Repo\n\nWorkflow automation with analytics."
    assert data["readme_snapshot"]["normalization_version"] == "story-3.4-v1"
    assert data["analysis_artifact"]["provider_name"] == "StaticAnalysisProvider"
    assert data["analysis_artifact"]["payload"]["analysis"]["missing_feature_signals"] == [
        "Missing SSO"
    ]
    assert data["processing"]["intake_created_at"] == "2026-03-09T12:00:00Z"
    assert data["processing"]["failure"] is None
    assert data["is_starred"] is False
    assert data["user_tags"] == []


def test_get_repository_exploration_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/repositories/999999999")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "repository_not_found"
    assert "999999999" in data["error"]["message"]


def test_list_repository_catalog_returns_paginated_results(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_catalog(db_session)

    response = client.get("/api/v1/repositories")
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 30
    assert data["total_pages"] == 1
    assert [item["github_repository_id"] for item in data["items"]] == [701]
    assert data["items"][0]["full_name"] == "alpha/growth-engine"
    assert data["items"][0]["intake_status"] == "completed"
    assert data["items"][0]["monetization_potential"] == "high"
    assert data["items"][0]["has_readme_artifact"] is True
    assert data["items"][0]["has_analysis_artifact"] is False
    assert data["items"][0]["is_starred"] is False
    assert data["items"][0]["user_tags"] == []


def test_get_repository_exploration_surfaces_failure_context(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime(2026, 3, 9, 16, 0, tzinfo=timezone.utc)
    db_session.add(
        RepositoryIntake(
            github_repository_id=703,
            source_provider="github",
            owner_login="gamma",
            repository_name="failure-repo",
            full_name="gamma/failure-repo",
            repository_description="Repository with failed analysis",
            discovery_source=RepositoryDiscoverySource.FIREHOSE,
            firehose_discovery_mode=RepositoryFirehoseMode.TRENDING,
            queue_status=RepositoryQueueStatus.COMPLETED,
            triage_status=RepositoryTriageStatus.ACCEPTED,
            analysis_status=RepositoryAnalysisStatus.FAILED,
            stargazers_count=88,
            forks_count=14,
            discovered_at=now,
            queue_created_at=now,
            processing_started_at=now,
            processing_completed_at=now,
            status_updated_at=now,
            triaged_at=now,
            analysis_started_at=now,
            analysis_last_attempted_at=now,
            analysis_last_failed_at=now,
            pushed_at=now,
            analysis_failure_message="Gateway rate limit while analyzing repository.",
        )
    )
    db_session.commit()

    response = client.get("/api/v1/repositories/703")

    assert response.status_code == 200
    data = response.json()
    assert data["analysis_status"] == "failed"
    assert data["processing"]["analysis_failed_at"] == "2026-03-09T16:00:00Z"
    assert data["processing"]["failure"] == {
        "stage": "analysis",
        "step": "analysis",
        "upstream_source": "firehose",
        "error_code": None,
        "error_message": "Gateway rate limit while analyzing repository.",
        "failed_at": "2026-03-09T16:00:00Z",
    }


def test_list_repository_catalog_supports_filters_and_search(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_catalog(db_session)

    response = client.get(
        "/api/v1/repositories",
        params={
            "search": "growth",
            "discovery_source": "firehose",
            "triage_status": "accepted",
            "analysis_status": "completed",
            "monetization_potential": "high",
            "min_stars": 500,
            "max_stars": 1000,
            "sort_by": "stars",
            "sort_order": "desc",
        },
    )
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 1
    assert [item["github_repository_id"] for item in data["items"]] == [701]


def test_list_repository_catalog_treats_like_special_characters_as_literals(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_catalog(db_session)
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    db_session.add_all(
        [
            RepositoryIntake(
                github_repository_id=703,
                source_provider="github",
                owner_login="gamma",
                repository_name="test%repo",
                full_name="gamma/test%repo",
                repository_description="Contains percent literal",
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                firehose_discovery_mode=RepositoryFirehoseMode.TRENDING,
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.COMPLETED,
                stargazers_count=700,
                forks_count=70,
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
                github_repository_id=704,
                source_provider="github",
                owner_login="delta",
                repository_name="user_repo",
                full_name="delta/user_repo",
                repository_description="Contains underscore literal",
                discovery_source=RepositoryDiscoverySource.BACKFILL,
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.COMPLETED,
                stargazers_count=650,
                forks_count=65,
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
                github_repository_id=705,
                source_provider="github",
                owner_login="epsilon",
                repository_name=r"slash\repo",
                full_name=r"epsilon/slash\repo",
                repository_description=r"Path matcher folder\repo",
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                firehose_discovery_mode=RepositoryFirehoseMode.NEW,
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.COMPLETED,
                stargazers_count=600,
                forks_count=60,
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
    db_session.commit()

    percent_response = client.get("/api/v1/repositories", params={"search": "test%repo"})
    assert percent_response.status_code == 200
    assert [item["github_repository_id"] for item in percent_response.json()["items"]] == [703]

    underscore_response = client.get("/api/v1/repositories", params={"search": "user_repo"})
    assert underscore_response.status_code == 200
    assert [item["github_repository_id"] for item in underscore_response.json()["items"]] == [704]

    backslash_response = client.get("/api/v1/repositories", params={"search": r"folder\repo"})
    assert backslash_response.status_code == 200
    assert [item["github_repository_id"] for item in backslash_response.json()["items"]] == [705]


def test_list_repository_catalog_supports_star_range_filtering(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_catalog(db_session)

    response = client.get(
        "/api/v1/repositories",
        params={"min_stars": 800, "max_stars": 950},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 1
    assert [item["github_repository_id"] for item in data["items"]] == [701]


def test_list_repository_catalog_returns_structured_error_for_invalid_page_size(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/repositories", params={"page_size": 101})
    assert response.status_code == 400
    data = response.json()

    assert data["error"]["code"] == "invalid_repository_catalog_query"
    assert data["error"]["details"]["field"] == "page_size"


def test_list_repository_catalog_rejects_invalid_star_range(client: TestClient) -> None:
    response = client.get(
        "/api/v1/repositories",
        params={"min_stars": 500, "max_stars": 400},
    )
    assert response.status_code == 400
    data = response.json()

    assert data["error"]["code"] == "invalid_repository_catalog_query"
    assert data["error"]["details"]["field"] == "max_stars"


def test_list_repository_catalog_returns_empty_items_for_excluding_filters(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_catalog(db_session)

    response = client.get(
        "/api/v1/repositories",
        params={"discovery_source": "firehose", "min_stars": 5000},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 0
    assert data["items"] == []
    assert data["total_pages"] == 0

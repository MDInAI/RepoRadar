from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine

from app.core.errors import AppError
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
    RepositoryTriageStatus,
    SQLModel,
)
from app.repositories.repository_exploration_repository import RepositoryExplorationRepository
from app.services.repository_exploration_service import RepositoryExplorationService


def _make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'repository-exploration.db'}")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_repository_exploration_service_returns_joined_metadata_summary_and_artifacts(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 3, 9, 11, 0, tzinfo=timezone.utc)
    with _make_session(tmp_path) as session:
        session.add(
            RepositoryIntake(
                github_repository_id=707,
                owner_login="octocat",
                repository_name="analyze-me",
                full_name="octocat/analyze-me",
                repository_description="Automation platform for SaaS teams",
                stargazers_count=321,
                forks_count=45,
                pushed_at=now,
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                firehose_discovery_mode=RepositoryFirehoseMode.NEW,
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.COMPLETED,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
                triaged_at=now,
                analysis_started_at=now,
                analysis_completed_at=now,
                analysis_last_attempted_at=now,
            )
        )
        session.add(
            RepositoryAnalysisResult(
                github_repository_id=707,
                monetization_potential=RepositoryMonetizationPotential.HIGH,
                pros=["Clear workflow"],
                cons=["Pricing unclear"],
                missing_feature_signals=["Missing billing"],
                source_metadata={"readme_artifact_path": "data/readmes/707.md"},
                analyzed_at=now,
            )
        )
        session.add(
            RepositoryArtifact(
                github_repository_id=707,
                artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                runtime_relative_path="data/readmes/707.md",
                content_sha256="a" * 64,
                byte_size=128,
                content_type="text/markdown; charset=utf-8",
                source_kind="repository_readme",
                source_url="https://api.github.com/repos/octocat/analyze-me/readme",
                provenance_metadata={"normalization_version": "story-3.4-v1"},
                generated_at=now,
            )
        )
        session.add(
            RepositoryArtifact(
                github_repository_id=707,
                artifact_kind=RepositoryArtifactKind.ANALYSIS_RESULT,
                runtime_relative_path="data/analyses/707.json",
                content_sha256="b" * 64,
                byte_size=256,
                content_type="application/json",
                source_kind="repository_analysis",
                source_url="https://api.github.com/repos/octocat/analyze-me/readme",
                provenance_metadata={"analysis_provider": "StaticAnalysisProvider"},
                generated_at=now,
            )
        )
        session.commit()

        service = RepositoryExplorationService(RepositoryExplorationRepository(session))
        response = service.get_repository_exploration(707)

    assert response.github_repository_id == 707
    assert response.full_name == "octocat/analyze-me"
    assert response.stargazers_count == 321
    assert response.forks_count == 45
    assert response.pushed_at == now
    assert response.analysis_summary is not None
    assert response.analysis_summary.monetization_potential is RepositoryMonetizationPotential.HIGH
    assert response.has_readme_artifact is True
    assert response.has_analysis_artifact is True
    assert [artifact.runtime_relative_path for artifact in response.artifacts] == [
        "data/analyses/707.json",
        "data/readmes/707.md",
    ]


def test_repository_exploration_service_raises_not_found_for_missing_repository(
    tmp_path: Path,
) -> None:
    with _make_session(tmp_path) as session:
        service = RepositoryExplorationService(RepositoryExplorationRepository(session))
        with pytest.raises(AppError, match="was not found"):
            service.get_repository_exploration(999)

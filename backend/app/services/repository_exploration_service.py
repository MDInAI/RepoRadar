from __future__ import annotations

from app.core.errors import AppError
from app.models import RepositoryArtifactKind
from app.repositories.repository_exploration_repository import RepositoryExplorationRepository
from app.schemas.repository_exploration import (
    RepositoryAnalysisSummaryResponse,
    RepositoryArtifactRefResponse,
    RepositoryExplorationResponse,
)


class RepositoryExplorationService:
    def __init__(self, repository: RepositoryExplorationRepository) -> None:
        self.repository = repository

    def get_repository_exploration(
        self,
        github_repository_id: int,
    ) -> RepositoryExplorationResponse:
        record = self.repository.get_repository_exploration(github_repository_id)
        if record is None:
            raise AppError(
                message=f"Repository {github_repository_id} was not found.",
                code="repository_not_found",
                status_code=404,
                details={"github_repository_id": github_repository_id},
            )

        artifact_responses = [
            RepositoryArtifactRefResponse(
                artifact_kind=artifact.artifact_kind,
                runtime_relative_path=artifact.runtime_relative_path,
                content_sha256=artifact.content_sha256,
                byte_size=artifact.byte_size,
                content_type=artifact.content_type,
                source_kind=artifact.source_kind,
                source_url=artifact.source_url,
                generated_at=artifact.generated_at,
            )
            for artifact in record.artifacts
        ]
        artifact_kinds = {artifact.artifact_kind for artifact in record.artifacts}

        analysis_summary = None
        if record.analysis_summary is not None:
            analysis_summary = RepositoryAnalysisSummaryResponse(
                monetization_potential=record.analysis_summary.monetization_potential,
                pros=record.analysis_summary.pros,
                cons=record.analysis_summary.cons,
                missing_feature_signals=record.analysis_summary.missing_feature_signals,
                analyzed_at=record.analysis_summary.analyzed_at,
            )

        return RepositoryExplorationResponse(
            github_repository_id=record.github_repository_id,
            full_name=record.full_name,
            repository_description=record.repository_description,
            discovery_source=record.discovery_source,
            triage_status=record.triage_status,
            analysis_status=record.analysis_status,
            stargazers_count=record.stargazers_count,
            forks_count=record.forks_count,
            pushed_at=record.pushed_at,
            analysis_summary=analysis_summary,
            artifacts=artifact_responses,
            has_readme_artifact=RepositoryArtifactKind.README_SNAPSHOT in artifact_kinds,
            has_analysis_artifact=RepositoryArtifactKind.ANALYSIS_RESULT in artifact_kinds,
        )

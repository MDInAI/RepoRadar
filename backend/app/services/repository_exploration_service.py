from __future__ import annotations

from app.core.errors import AppError
from app.models import RepositoryArtifactKind
from app.repositories.repository_exploration_repository import (
    RepositoryCatalogListParams,
    RepositoryExplorationRepository,
)
from app.schemas.repository_exploration import (
    RepositoryAnalysisSummaryResponse,
    RepositoryArtifactRefResponse,
    RepositoryCatalogItemResponse,
    RepositoryCatalogPageResponse,
    RepositoryCatalogQueryParams,
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

    def list_repository_catalog(
        self,
        params: RepositoryCatalogQueryParams,
    ) -> RepositoryCatalogPageResponse:
        page = self.repository.list_repository_catalog(
            RepositoryCatalogListParams(
                page=params.page,
                page_size=params.page_size,
                search=params.search,
                discovery_source=params.discovery_source,
                triage_status=params.triage_status,
                analysis_status=params.analysis_status,
                monetization_potential=params.monetization_potential,
                min_stars=params.min_stars,
                max_stars=params.max_stars,
                sort_by=params.sort_by.value,
                sort_order=params.sort_order.value,
            )
        )

        return RepositoryCatalogPageResponse(
            items=[
                RepositoryCatalogItemResponse(
                    github_repository_id=item.github_repository_id,
                    full_name=item.full_name,
                    owner_login=item.owner_login,
                    repository_name=item.repository_name,
                    repository_description=item.repository_description,
                    stargazers_count=item.stargazers_count,
                    forks_count=item.forks_count,
                    pushed_at=item.pushed_at,
                    discovery_source=item.discovery_source,
                    triage_status=item.triage_status,
                    analysis_status=item.analysis_status,
                    monetization_potential=item.monetization_potential,
                    has_readme_artifact=item.has_readme_artifact,
                    has_analysis_artifact=item.has_analysis_artifact,
                )
                for item in page.items
            ],
            total=page.total,
            page=page.page,
            page_size=page.page_size,
            total_pages=page.total_pages,
        )

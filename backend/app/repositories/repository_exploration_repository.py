from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil

from sqlalchemy import exists, func, or_
from sqlmodel import Session, select

from app.models import (
    RepositoryAnalysisResult,
    RepositoryAnalysisStatus,
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryDiscoverySource,
    RepositoryIntake,
    RepositoryMonetizationPotential,
    RepositoryTriageStatus,
)


@dataclass(frozen=True, slots=True)
class RepositoryArtifactRefRecord:
    artifact_kind: RepositoryArtifactKind
    runtime_relative_path: str
    content_sha256: str
    byte_size: int
    content_type: str
    source_kind: str
    source_url: str | None
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class RepositoryAnalysisSummaryRecord:
    monetization_potential: RepositoryMonetizationPotential
    pros: list[str]
    cons: list[str]
    missing_feature_signals: list[str]
    analyzed_at: datetime


@dataclass(frozen=True, slots=True)
class RepositoryExplorationRecord:
    github_repository_id: int
    full_name: str
    repository_description: str | None
    discovery_source: RepositoryDiscoverySource
    triage_status: RepositoryTriageStatus
    analysis_status: RepositoryAnalysisStatus
    stargazers_count: int
    forks_count: int
    pushed_at: datetime | None
    analysis_summary: RepositoryAnalysisSummaryRecord | None
    artifacts: list[RepositoryArtifactRefRecord]


@dataclass(frozen=True, slots=True)
class RepositoryCatalogListParams:
    page: int
    page_size: int
    search: str | None
    discovery_source: RepositoryDiscoverySource | None
    triage_status: RepositoryTriageStatus | None
    analysis_status: RepositoryAnalysisStatus | None
    monetization_potential: RepositoryMonetizationPotential | None
    min_stars: int | None
    max_stars: int | None
    sort_by: str
    sort_order: str


@dataclass(frozen=True, slots=True)
class RepositoryCatalogItemRecord:
    github_repository_id: int
    full_name: str
    owner_login: str
    repository_name: str
    repository_description: str | None
    stargazers_count: int
    forks_count: int
    pushed_at: datetime | None
    discovery_source: RepositoryDiscoverySource
    triage_status: RepositoryTriageStatus
    analysis_status: RepositoryAnalysisStatus
    monetization_potential: RepositoryMonetizationPotential | None
    has_readme_artifact: bool
    has_analysis_artifact: bool


@dataclass(frozen=True, slots=True)
class RepositoryCatalogPageRecord:
    items: list[RepositoryCatalogItemRecord]
    total: int
    page: int
    page_size: int
    total_pages: int


class RepositoryExplorationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_repository_exploration(
        self, github_repository_id: int
    ) -> RepositoryExplorationRecord | None:
        intake = self.session.get(RepositoryIntake, github_repository_id)
        if intake is None:
            return None

        analysis_row = self.session.get(RepositoryAnalysisResult, github_repository_id)
        analysis_summary = None
        if analysis_row is not None:
            analysis_summary = RepositoryAnalysisSummaryRecord(
                monetization_potential=analysis_row.monetization_potential,
                pros=list(analysis_row.pros),
                cons=list(analysis_row.cons),
                missing_feature_signals=list(analysis_row.missing_feature_signals),
                analyzed_at=analysis_row.analyzed_at,
            )

        artifact_rows = self.session.exec(
            select(RepositoryArtifact)
            .where(RepositoryArtifact.github_repository_id == github_repository_id)
            .order_by(RepositoryArtifact.artifact_kind)
        ).all()
        artifacts = [
            RepositoryArtifactRefRecord(
                artifact_kind=row.artifact_kind,
                runtime_relative_path=row.runtime_relative_path,
                content_sha256=row.content_sha256,
                byte_size=row.byte_size,
                content_type=row.content_type,
                source_kind=row.source_kind,
                source_url=row.source_url,
                generated_at=row.generated_at,
            )
            for row in artifact_rows
        ]

        return RepositoryExplorationRecord(
            github_repository_id=intake.github_repository_id,
            full_name=intake.full_name,
            repository_description=intake.repository_description,
            discovery_source=intake.discovery_source,
            triage_status=intake.triage_status,
            analysis_status=intake.analysis_status,
            stargazers_count=intake.stargazers_count,
            forks_count=intake.forks_count,
            pushed_at=intake.pushed_at,
            analysis_summary=analysis_summary,
            artifacts=artifacts,
        )

    def list_repository_catalog(
        self,
        params: RepositoryCatalogListParams,
    ) -> RepositoryCatalogPageRecord:
        filters: list[object] = []
        if params.discovery_source is not None:
            filters.append(RepositoryIntake.discovery_source == params.discovery_source)
        if params.triage_status is not None:
            filters.append(RepositoryIntake.triage_status == params.triage_status)
        if params.analysis_status is not None:
            filters.append(RepositoryIntake.analysis_status == params.analysis_status)
        if params.triage_status is None and params.analysis_status is None:
            filters.append(RepositoryIntake.triage_status == RepositoryTriageStatus.ACCEPTED)
            filters.append(RepositoryIntake.analysis_status == RepositoryAnalysisStatus.COMPLETED)
        if params.monetization_potential is not None:
            filters.append(
                RepositoryAnalysisResult.monetization_potential == params.monetization_potential
            )
        if params.min_stars is not None:
            filters.append(RepositoryIntake.stargazers_count >= params.min_stars)
        if params.max_stars is not None:
            filters.append(RepositoryIntake.stargazers_count <= params.max_stars)
        if params.search:
            escaped_search = (
                params.search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            search_pattern = f"%{escaped_search}%"
            filters.append(
                or_(
                    RepositoryIntake.full_name.like(search_pattern, escape="\\"),
                    RepositoryIntake.repository_description.like(search_pattern, escape="\\"),
                )
            )

        join_clause = (
            RepositoryIntake.github_repository_id == RepositoryAnalysisResult.github_repository_id
        )
        readme_exists = exists(
            select(RepositoryArtifact.github_repository_id).where(
                RepositoryArtifact.github_repository_id == RepositoryIntake.github_repository_id,
                RepositoryArtifact.artifact_kind == RepositoryArtifactKind.README_SNAPSHOT,
            )
        )
        analysis_exists = exists(
            select(RepositoryArtifact.github_repository_id).where(
                RepositoryArtifact.github_repository_id == RepositoryIntake.github_repository_id,
                RepositoryArtifact.artifact_kind == RepositoryArtifactKind.ANALYSIS_RESULT,
            )
        )
        sort_column_map = {
            "stars": RepositoryIntake.stargazers_count,
            "forks": RepositoryIntake.forks_count,
            "pushed_at": RepositoryIntake.pushed_at,
            "ingested_at": RepositoryIntake.discovered_at,
        }
        sort_column = sort_column_map.get(params.sort_by)
        if sort_column is None:
            raise ValueError(f"Unsupported sort_by value: {params.sort_by!r}")
        sort_expression = sort_column.asc() if params.sort_order == "asc" else sort_column.desc()
        tie_breaker = (
            RepositoryIntake.github_repository_id.asc()
            if params.sort_order == "asc"
            else RepositoryIntake.github_repository_id.desc()
        )

        count_query = (
            select(func.count(RepositoryIntake.github_repository_id))
            .select_from(RepositoryIntake)
            .outerjoin(RepositoryAnalysisResult, join_clause)
        )
        if filters:
            count_query = count_query.where(*filters)
        total = int(self.session.exec(count_query).one())

        query = (
            select(
                RepositoryIntake.github_repository_id,
                RepositoryIntake.full_name,
                RepositoryIntake.owner_login,
                RepositoryIntake.repository_name,
                RepositoryIntake.repository_description,
                RepositoryIntake.stargazers_count,
                RepositoryIntake.forks_count,
                RepositoryIntake.pushed_at,
                RepositoryIntake.discovery_source,
                RepositoryIntake.triage_status,
                RepositoryIntake.analysis_status,
                RepositoryAnalysisResult.monetization_potential,
                readme_exists.label("has_readme_artifact"),
                analysis_exists.label("has_analysis_artifact"),
            )
            .select_from(RepositoryIntake)
            .outerjoin(RepositoryAnalysisResult, join_clause)
            .order_by(sort_expression, tie_breaker)
            .offset((params.page - 1) * params.page_size)
            .limit(params.page_size)
        )
        if filters:
            query = query.where(*filters)

        rows = self.session.exec(query).all()
        items = [
            RepositoryCatalogItemRecord(
                github_repository_id=row.github_repository_id,
                full_name=row.full_name,
                owner_login=row.owner_login,
                repository_name=row.repository_name,
                repository_description=row.repository_description,
                stargazers_count=row.stargazers_count,
                forks_count=row.forks_count,
                pushed_at=row.pushed_at,
                discovery_source=row.discovery_source,
                triage_status=row.triage_status,
                analysis_status=row.analysis_status,
                monetization_potential=row.monetization_potential,
                has_readme_artifact=bool(row.has_readme_artifact),
                has_analysis_artifact=bool(row.has_analysis_artifact),
            )
            for row in rows
        ]

        return RepositoryCatalogPageRecord(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            total_pages=ceil(total / params.page_size) if total else 0,
        )

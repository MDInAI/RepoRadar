from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil
from collections import defaultdict

from sqlalchemy import case, exists, func, or_
from sqlmodel import Session, select

from app.models import (
    RepositoryAnalysisResult,
    RepositoryAnalysisStatus,
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryDiscoverySource,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryUserCuration,
    RepositoryUserTag,
    RepositoryMonetizationPotential,
    RepositoryTriageExplanation,
    RepositoryTriageExplanationKind,
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
    provenance_metadata: dict[str, object]
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class RepositoryAnalysisSummaryRecord:
    monetization_potential: RepositoryMonetizationPotential
    pros: list[str]
    cons: list[str]
    missing_feature_signals: list[str]
    source_metadata: dict[str, object]
    analyzed_at: datetime


@dataclass(frozen=True, slots=True)
class RepositoryTriageExplanationRecord:
    kind: RepositoryTriageExplanationKind
    summary: str
    matched_include_rules: list[str]
    matched_exclude_rules: list[str]
    explained_at: datetime


@dataclass(frozen=True, slots=True)
class RepositoryTriageRecord:
    triage_status: RepositoryTriageStatus
    triaged_at: datetime | None
    explanation: RepositoryTriageExplanationRecord | None


@dataclass(frozen=True, slots=True)
class RepositoryExplorationRecord:
    github_repository_id: int
    source_provider: str
    owner_login: str
    repository_name: str
    full_name: str
    repository_description: str | None
    discovery_source: RepositoryDiscoverySource
    queue_status: RepositoryQueueStatus
    triage_status: RepositoryTriageStatus
    analysis_status: RepositoryAnalysisStatus
    stargazers_count: int
    forks_count: int
    discovered_at: datetime
    status_updated_at: datetime
    pushed_at: datetime | None
    triage: RepositoryTriageRecord
    analysis_summary: RepositoryAnalysisSummaryRecord | None
    artifacts: list[RepositoryArtifactRefRecord]
    is_starred: bool
    user_tags: list[str]


@dataclass(frozen=True, slots=True)
class RepositoryCatalogListParams:
    page: int
    page_size: int
    search: str | None
    discovery_source: RepositoryDiscoverySource | None
    queue_status: RepositoryQueueStatus | None
    triage_status: RepositoryTriageStatus | None
    analysis_status: RepositoryAnalysisStatus | None
    has_failures: bool
    monetization_potential: RepositoryMonetizationPotential | None
    min_stars: int | None
    max_stars: int | None
    starred_only: bool
    user_tag: str | None
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
    queue_status: RepositoryQueueStatus
    triage_status: RepositoryTriageStatus
    analysis_status: RepositoryAnalysisStatus
    queue_created_at: datetime | None
    processing_started_at: datetime | None
    processing_completed_at: datetime | None
    last_failed_at: datetime | None
    analysis_failure_code: str | None
    analysis_failure_message: str | None
    monetization_potential: RepositoryMonetizationPotential | None
    has_readme_artifact: bool
    has_analysis_artifact: bool
    is_starred: bool
    user_tags: list[str]


@dataclass(frozen=True, slots=True)
class RepositoryCatalogPageRecord:
    items: list[RepositoryCatalogItemRecord]
    total: int
    page: int
    page_size: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class RepositoryBacklogSummaryRecord:
    queue: dict[str, int]
    triage: dict[str, int]
    analysis: dict[str, int]


class RepositoryExplorationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_repository_exploration(
        self, github_repository_id: int
    ) -> RepositoryExplorationRecord | None:
        intake = self.session.get(RepositoryIntake, github_repository_id)
        if intake is None:
            return None

        curation_row = self.session.get(RepositoryUserCuration, github_repository_id)
        tag_rows = self.session.exec(
            select(RepositoryUserTag)
            .where(RepositoryUserTag.github_repository_id == github_repository_id)
            .order_by(RepositoryUserTag.created_at.asc(), RepositoryUserTag.id.asc())
        ).all()

        analysis_row = self.session.get(RepositoryAnalysisResult, github_repository_id)
        analysis_summary = None
        if analysis_row is not None:
            analysis_summary = RepositoryAnalysisSummaryRecord(
                monetization_potential=analysis_row.monetization_potential,
                pros=list(analysis_row.pros),
                cons=list(analysis_row.cons),
                missing_feature_signals=list(analysis_row.missing_feature_signals),
                source_metadata=dict(analysis_row.source_metadata),
                analyzed_at=analysis_row.analyzed_at,
            )

        explanation_row = self.session.get(RepositoryTriageExplanation, github_repository_id)
        explanation = None
        if (
            explanation_row is not None
            and intake.triage_status is not RepositoryTriageStatus.PENDING
            and intake.triaged_at is not None
        ):
            explanation = RepositoryTriageExplanationRecord(
                kind=explanation_row.explanation_kind,
                summary=explanation_row.explanation_summary,
                matched_include_rules=list(explanation_row.matched_include_rules),
                matched_exclude_rules=list(explanation_row.matched_exclude_rules),
                explained_at=explanation_row.explained_at,
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
                provenance_metadata=dict(row.provenance_metadata),
                generated_at=row.generated_at,
            )
            for row in artifact_rows
        ]

        return RepositoryExplorationRecord(
            github_repository_id=intake.github_repository_id,
            source_provider=intake.source_provider,
            owner_login=intake.owner_login,
            repository_name=intake.repository_name,
            full_name=intake.full_name,
            repository_description=intake.repository_description,
            discovery_source=intake.discovery_source,
            queue_status=intake.queue_status,
            triage_status=intake.triage_status,
            analysis_status=intake.analysis_status,
            stargazers_count=intake.stargazers_count,
            forks_count=intake.forks_count,
            discovered_at=intake.discovered_at,
            status_updated_at=intake.status_updated_at,
            pushed_at=intake.pushed_at,
            triage=RepositoryTriageRecord(
                triage_status=intake.triage_status,
                triaged_at=intake.triaged_at,
                explanation=explanation,
            ),
            analysis_summary=analysis_summary,
            artifacts=artifacts,
            is_starred=curation_row.is_starred if curation_row is not None else False,
            user_tags=[row.tag_label for row in tag_rows],
        )

    def list_repository_catalog(
        self,
        params: RepositoryCatalogListParams,
    ) -> RepositoryCatalogPageRecord:
        filters: list[object] = []
        if params.discovery_source is not None:
            filters.append(RepositoryIntake.discovery_source == params.discovery_source)
        if params.queue_status is not None:
            filters.append(RepositoryIntake.queue_status == params.queue_status)
        if params.triage_status is not None:
            filters.append(RepositoryIntake.triage_status == params.triage_status)
        if params.analysis_status is not None:
            filters.append(RepositoryIntake.analysis_status == params.analysis_status)
        if params.has_failures:
            filters.append(
                or_(
                    RepositoryIntake.queue_status == RepositoryQueueStatus.FAILED,
                    RepositoryIntake.analysis_status == RepositoryAnalysisStatus.FAILED,
                )
            )
        if (
            params.queue_status is None
            and params.triage_status is None
            and params.analysis_status is None
            and not params.has_failures
        ):
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
        if params.starred_only:
            filters.append(RepositoryUserCuration.is_starred.is_(True))
        if params.user_tag:
            filters.append(
                exists(
                    select(RepositoryUserTag.id).where(
                        RepositoryUserTag.github_repository_id
                        == RepositoryIntake.github_repository_id,
                        RepositoryUserTag.tag_label == params.user_tag,
                    )
                )
            )
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
        curation_join_clause = (
            RepositoryIntake.github_repository_id == RepositoryUserCuration.github_repository_id
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
            .outerjoin(RepositoryUserCuration, curation_join_clause)
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
                RepositoryIntake.queue_status,
                RepositoryIntake.triage_status,
                RepositoryIntake.analysis_status,
                RepositoryIntake.queue_created_at,
                func.coalesce(
                    RepositoryIntake.analysis_started_at,
                    RepositoryIntake.processing_started_at,
                ).label("processing_started_at"),
                func.coalesce(
                    RepositoryIntake.analysis_completed_at,
                    RepositoryIntake.processing_completed_at,
                ).label("processing_completed_at"),
                func.coalesce(
                    RepositoryIntake.analysis_last_failed_at,
                    RepositoryIntake.last_failed_at,
                ).label("last_failed_at"),
                RepositoryIntake.analysis_failure_code,
                RepositoryIntake.analysis_failure_message,
                RepositoryAnalysisResult.monetization_potential,
                readme_exists.label("has_readme_artifact"),
                analysis_exists.label("has_analysis_artifact"),
                RepositoryUserCuration.is_starred.label("is_starred"),
            )
            .select_from(RepositoryIntake)
            .outerjoin(RepositoryAnalysisResult, join_clause)
            .outerjoin(RepositoryUserCuration, curation_join_clause)
            .order_by(sort_expression, tie_breaker)
            .offset((params.page - 1) * params.page_size)
            .limit(params.page_size)
        )
        if filters:
            query = query.where(*filters)

        rows = self.session.exec(query).all()
        repository_ids = [row.github_repository_id for row in rows]
        user_tags_by_repository_id: dict[int, list[str]] = defaultdict(list)
        if repository_ids:
            tag_rows = self.session.exec(
                select(RepositoryUserTag)
                .where(RepositoryUserTag.github_repository_id.in_(repository_ids))
                .order_by(
                    RepositoryUserTag.github_repository_id.asc(),
                    RepositoryUserTag.created_at.asc(),
                    RepositoryUserTag.id.asc(),
                )
            ).all()
            for tag_row in tag_rows:
                user_tags_by_repository_id[tag_row.github_repository_id].append(tag_row.tag_label)
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
                queue_status=row.queue_status,
                triage_status=row.triage_status,
                analysis_status=row.analysis_status,
                queue_created_at=row.queue_created_at,
                processing_started_at=row.processing_started_at,
                processing_completed_at=row.processing_completed_at,
                last_failed_at=row.last_failed_at,
                analysis_failure_code=(
                    row.analysis_failure_code.value
                    if row.analysis_failure_code is not None
                    else None
                ),
                analysis_failure_message=row.analysis_failure_message,
                monetization_potential=row.monetization_potential,
                has_readme_artifact=bool(row.has_readme_artifact),
                has_analysis_artifact=bool(row.has_analysis_artifact),
                is_starred=bool(row.is_starred),
                user_tags=user_tags_by_repository_id.get(row.github_repository_id, []),
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

    def get_repository_backlog_summary(self) -> RepositoryBacklogSummaryRecord:
        queue_statuses = (
            RepositoryQueueStatus.PENDING,
            RepositoryQueueStatus.IN_PROGRESS,
            RepositoryQueueStatus.COMPLETED,
            RepositoryQueueStatus.FAILED,
        )
        triage_statuses = (
            RepositoryTriageStatus.PENDING,
            RepositoryTriageStatus.ACCEPTED,
            RepositoryTriageStatus.REJECTED,
        )
        analysis_statuses = (
            RepositoryAnalysisStatus.PENDING,
            RepositoryAnalysisStatus.IN_PROGRESS,
            RepositoryAnalysisStatus.COMPLETED,
            RepositoryAnalysisStatus.FAILED,
        )
        summary_columns = [
            *self._build_summary_columns("queue", RepositoryIntake.queue_status, queue_statuses),
            *self._build_summary_columns(
                "triage", RepositoryIntake.triage_status, triage_statuses
            ),
            *self._build_summary_columns(
                "analysis", RepositoryIntake.analysis_status, analysis_statuses
            ),
        ]
        summary_row = self.session.exec(select(*summary_columns).select_from(RepositoryIntake)).one()

        return RepositoryBacklogSummaryRecord(
            queue=self._read_summary_counts(summary_row, "queue", queue_statuses),
            triage=self._read_summary_counts(summary_row, "triage", triage_statuses),
            analysis=self._read_summary_counts(summary_row, "analysis", analysis_statuses),
        )

    def _build_summary_columns(
        self, prefix: str, column: object, statuses: tuple[object, ...]
    ) -> list[object]:
        return [
            func.coalesce(
                func.sum(case((column == status, 1), else_=0)),
                0,
            ).label(f"{prefix}_{status.value}")
            for status in statuses
            if hasattr(status, "value")
        ]

    def _read_summary_counts(
        self, row: object, prefix: str, statuses: tuple[object, ...]
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for status in statuses:
            if not hasattr(status, "value"):
                continue
            label = f"{prefix}_{status.value}"
            counts[status.value] = int(getattr(row, label))
        return counts

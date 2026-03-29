from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil
from collections import defaultdict

from sqlalchemy import case, exists, func, or_
from sqlmodel import Session, select

from app.models import (
    IdeaFamilyMembership,
    IdeaSearch,
    IdeaSearchDiscovery,
    RepositoryAnalysisResult,
    RepositoryAnalysisStatus,
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryCategory,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
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
    category: RepositoryCategory | None
    category_confidence_score: int | None
    agent_tags: list[str]
    suggested_new_categories: list[str]
    suggested_new_tags: list[str]
    pros: list[str]
    cons: list[str]
    missing_feature_signals: list[str]
    problem_statement: str | None
    target_customer: str | None
    product_type: str | None
    business_model_guess: str | None
    technical_stack: str | None
    target_audience: str | None
    open_problems: str | None
    competitors: str | None
    confidence_score: int | None
    recommended_action: str | None
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
class ScoutDiscoveryRecord:
    idea_search_id: int
    idea_text: str
    query_index: int
    query_text: str
    discovered_at: datetime


@dataclass(frozen=True, slots=True)
class RepositoryExplorationRecord:
    github_repository_id: int
    source_provider: str
    owner_login: str
    repository_name: str
    full_name: str
    repository_description: str | None
    discovery_source: RepositoryDiscoverySource
    firehose_discovery_mode: RepositoryFirehoseMode | None
    intake_status: RepositoryQueueStatus
    triage_status: RepositoryTriageStatus
    analysis_status: RepositoryAnalysisStatus
    stargazers_count: int
    forks_count: int
    github_created_at: datetime | None
    discovered_at: datetime
    status_updated_at: datetime
    pushed_at: datetime | None
    category: RepositoryCategory | None
    agent_tags: list[str]
    triage: RepositoryTriageRecord
    analysis_summary: RepositoryAnalysisSummaryRecord | None
    artifacts: list[RepositoryArtifactRefRecord]
    processing: "RepositoryProcessingRecord"
    is_starred: bool
    user_tags: list[str]
    idea_family_ids: list[int]
    scout_context: ScoutDiscoveryRecord | None = None


@dataclass(frozen=True, slots=True)
class RepositoryCatalogListParams:
    page: int
    page_size: int
    search: str | None = None
    discovery_source: RepositoryDiscoverySource | None = None
    queue_status: RepositoryQueueStatus | None = None
    triage_status: RepositoryTriageStatus | None = None
    analysis_status: RepositoryAnalysisStatus | None = None
    has_failures: bool = False
    category: RepositoryCategory | None = None
    agent_tag: str | None = None
    monetization_potential: RepositoryMonetizationPotential | None = None
    min_stars: int | None = None
    max_stars: int | None = None
    starred_only: bool = False
    user_tag: str | None = None
    idea_family_id: int | None = None
    idea_search_id: int | None = None
    sort_by: str = "stars"
    sort_order: str = "desc"


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
    firehose_discovery_mode: RepositoryFirehoseMode | None
    intake_status: RepositoryQueueStatus
    triage_status: RepositoryTriageStatus
    analysis_status: RepositoryAnalysisStatus
    queue_created_at: datetime | None
    processing_started_at: datetime | None
    processing_completed_at: datetime | None
    intake_failed_at: datetime | None
    analysis_failed_at: datetime | None
    failure: "RepositoryFailureContextRecord | None"
    category: RepositoryCategory | None
    category_confidence_score: int | None
    confidence_score: int | None
    analysis_outcome: str | None
    agent_tags: list[str]
    suggested_new_tags: list[str]
    monetization_potential: RepositoryMonetizationPotential | None
    has_readme_artifact: bool
    has_analysis_artifact: bool
    is_starred: bool
    user_tags: list[str]
    idea_family_ids: list[int]
    scout_context: ScoutDiscoveryRecord | None = None


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


@dataclass(frozen=True, slots=True)
class RepositoryFailureContextRecord:
    stage: str
    step: str
    upstream_source: str
    error_code: str | None
    error_message: str | None
    failed_at: datetime | None


@dataclass(frozen=True, slots=True)
class RepositoryProcessingRecord:
    intake_created_at: datetime | None
    intake_started_at: datetime | None
    intake_completed_at: datetime | None
    intake_failed_at: datetime | None
    triaged_at: datetime | None
    analysis_started_at: datetime | None
    analysis_completed_at: datetime | None
    analysis_last_attempted_at: datetime | None
    analysis_failed_at: datetime | None
    failure: RepositoryFailureContextRecord | None


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
        family_rows = self.session.exec(
            select(IdeaFamilyMembership)
            .where(IdeaFamilyMembership.github_repository_id == github_repository_id)
        ).all()

        scout_context = (
            self._fetch_scout_context(github_repository_id)
            if intake.discovery_source is RepositoryDiscoverySource.IDEA_SCOUT
            else None
        )

        analysis_row = self.session.get(RepositoryAnalysisResult, github_repository_id)
        analysis_summary = None
        if analysis_row is not None:
            analysis_summary = RepositoryAnalysisSummaryRecord(
                monetization_potential=analysis_row.monetization_potential,
                category=analysis_row.category,
                category_confidence_score=analysis_row.category_confidence_score,
                agent_tags=list(analysis_row.agent_tags),
                suggested_new_categories=list(analysis_row.suggested_new_categories),
                suggested_new_tags=list(analysis_row.suggested_new_tags),
                pros=list(analysis_row.pros),
                cons=list(analysis_row.cons),
                missing_feature_signals=list(analysis_row.missing_feature_signals),
                problem_statement=analysis_row.problem_statement,
                target_customer=analysis_row.target_customer,
                product_type=analysis_row.product_type,
                business_model_guess=analysis_row.business_model_guess,
                technical_stack=analysis_row.technical_stack,
                target_audience=analysis_row.target_audience,
                open_problems=analysis_row.open_problems,
                competitors=analysis_row.competitors,
                confidence_score=analysis_row.confidence_score,
                recommended_action=analysis_row.recommended_action,
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
            firehose_discovery_mode=intake.firehose_discovery_mode,
            intake_status=intake.queue_status,
            triage_status=intake.triage_status,
            analysis_status=intake.analysis_status,
            stargazers_count=intake.stargazers_count,
            forks_count=intake.forks_count,
            github_created_at=intake.github_created_at,
            discovered_at=intake.discovered_at,
            status_updated_at=intake.status_updated_at,
            pushed_at=intake.pushed_at,
            category=analysis_row.category if analysis_row is not None else None,
            agent_tags=self._build_agent_tags(
                analysis_row.agent_tags if analysis_row is not None else [],
                discovery_source=intake.discovery_source,
                firehose_discovery_mode=intake.firehose_discovery_mode,
            ),
            triage=RepositoryTriageRecord(
                triage_status=intake.triage_status,
                triaged_at=intake.triaged_at,
                explanation=explanation,
            ),
            analysis_summary=analysis_summary,
            artifacts=artifacts,
            processing=RepositoryProcessingRecord(
                intake_created_at=intake.queue_created_at,
                intake_started_at=intake.processing_started_at,
                intake_completed_at=intake.processing_completed_at,
                intake_failed_at=(
                    intake.last_failed_at
                    if intake.queue_status is RepositoryQueueStatus.FAILED
                    else None
                ),
                triaged_at=intake.triaged_at,
                analysis_started_at=intake.analysis_started_at,
                analysis_completed_at=intake.analysis_completed_at,
                analysis_last_attempted_at=intake.analysis_last_attempted_at,
                analysis_failed_at=intake.analysis_last_failed_at,
                failure=self._build_failure_context(intake),
            ),
            is_starred=curation_row.is_starred if curation_row is not None else False,
            user_tags=[row.tag_label for row in tag_rows],
            idea_family_ids=[row.idea_family_id for row in family_rows],
            scout_context=scout_context,
        )

    def list_repository_catalog(
        self,
        params: RepositoryCatalogListParams,
    ) -> RepositoryCatalogPageRecord:
        filters: list[object] = []
        scout_scoped_view = params.discovery_source is RepositoryDiscoverySource.IDEA_SCOUT or (
            params.agent_tag is not None and params.agent_tag.strip().lower() == "idea_scout"
        )
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
            and params.idea_search_id is None
            and not scout_scoped_view
        ):
            filters.append(RepositoryIntake.triage_status == RepositoryTriageStatus.ACCEPTED)
            filters.append(RepositoryIntake.analysis_status == RepositoryAnalysisStatus.COMPLETED)
        if params.category is not None:
            filters.append(RepositoryAnalysisResult.category == params.category)
        if params.agent_tag:
            normalized_agent_tag = params.agent_tag.strip().lower()
            escaped_agent_tag = (
                normalized_agent_tag.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            agent_tag_filter = RepositoryAnalysisResult.agent_tags.like(
                f'%"{escaped_agent_tag}"%',
                escape="\\",
            )
            if normalized_agent_tag == "idea_scout":
                agent_tag_filter = or_(
                    agent_tag_filter,
                    RepositoryIntake.discovery_source == RepositoryDiscoverySource.IDEA_SCOUT,
                )
            if normalized_agent_tag in {
                RepositoryFirehoseMode.NEW.value,
                RepositoryFirehoseMode.TRENDING.value,
            }:
                agent_tag_filter = or_(
                    agent_tag_filter,
                    RepositoryIntake.firehose_discovery_mode
                    == RepositoryFirehoseMode(normalized_agent_tag),
                )
            filters.append(agent_tag_filter)
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
        if params.idea_family_id:
            filters.append(
                exists(
                    select(IdeaFamilyMembership.id).where(
                        IdeaFamilyMembership.github_repository_id
                        == RepositoryIntake.github_repository_id,
                        IdeaFamilyMembership.idea_family_id == params.idea_family_id,
                    )
                )
            )
        if params.idea_search_id:
            filters.append(
                exists(
                    select(IdeaSearchDiscovery.id).where(
                        IdeaSearchDiscovery.github_repository_id
                        == RepositoryIntake.github_repository_id,
                        IdeaSearchDiscovery.idea_search_id == params.idea_search_id,
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
                RepositoryIntake.firehose_discovery_mode,
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
                RepositoryIntake.last_failed_at.label("intake_failed_at"),
                RepositoryIntake.analysis_last_failed_at.label("analysis_failed_at"),
                RepositoryIntake.analysis_failure_code,
                RepositoryIntake.analysis_failure_message,
                RepositoryAnalysisResult.category,
                RepositoryAnalysisResult.category_confidence_score,
                RepositoryAnalysisResult.confidence_score,
                RepositoryAnalysisResult.source_metadata,
                RepositoryAnalysisResult.agent_tags,
                RepositoryAnalysisResult.suggested_new_tags,
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
        idea_family_ids_by_repository_id: dict[int, list[int]] = defaultdict(list)
        scout_context_by_repository_id: dict[int, ScoutDiscoveryRecord] = {}
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

            family_rows = self.session.exec(
                select(IdeaFamilyMembership)
                .where(IdeaFamilyMembership.github_repository_id.in_(repository_ids))
                .order_by(IdeaFamilyMembership.github_repository_id.asc())
            ).all()
            for family_row in family_rows:
                idea_family_ids_by_repository_id[family_row.github_repository_id].append(family_row.idea_family_id)

            scout_ids = [
                row.github_repository_id
                for row in rows
                if row.discovery_source is RepositoryDiscoverySource.IDEA_SCOUT
            ]
            if scout_ids:
                scout_rows = self.session.exec(
                    select(
                        IdeaSearchDiscovery.github_repository_id,
                        IdeaSearchDiscovery.idea_search_id,
                        IdeaSearchDiscovery.query_index,
                        IdeaSearchDiscovery.query_text,
                        IdeaSearchDiscovery.discovered_at,
                        IdeaSearch.idea_text,
                    )
                    .join(IdeaSearch, IdeaSearchDiscovery.idea_search_id == IdeaSearch.id)
                    .where(IdeaSearchDiscovery.github_repository_id.in_(scout_ids))
                    .order_by(IdeaSearchDiscovery.github_repository_id.asc())
                ).all()
                for scout_row in scout_rows:
                    repo_id = scout_row.github_repository_id
                    if repo_id not in scout_context_by_repository_id:
                        scout_context_by_repository_id[repo_id] = ScoutDiscoveryRecord(
                            idea_search_id=scout_row.idea_search_id,
                            idea_text=scout_row.idea_text,
                            query_index=scout_row.query_index,
                            query_text=scout_row.query_text,
                            discovered_at=scout_row.discovered_at,
                        )

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
                firehose_discovery_mode=row.firehose_discovery_mode,
                intake_status=row.queue_status,
                triage_status=row.triage_status,
                analysis_status=row.analysis_status,
                queue_created_at=row.queue_created_at,
                processing_started_at=row.processing_started_at,
                processing_completed_at=row.processing_completed_at,
                intake_failed_at=row.intake_failed_at,
                analysis_failed_at=row.analysis_failed_at,
                failure=self._build_catalog_failure_context(
                    intake_status=row.queue_status,
                    analysis_status=row.analysis_status,
                    discovery_source=row.discovery_source,
                    analysis_failure_code=(
                        row.analysis_failure_code.value
                        if row.analysis_failure_code is not None
                        else None
                    ),
                    analysis_failure_message=row.analysis_failure_message,
                    intake_failed_at=row.intake_failed_at,
                    analysis_failed_at=row.analysis_failed_at,
                ),
                category=row.category,
                category_confidence_score=row.category_confidence_score,
                confidence_score=row.confidence_score,
                analysis_outcome=(
                    row.source_metadata.get("analysis_outcome")
                    if isinstance(row.source_metadata, dict)
                    and isinstance(row.source_metadata.get("analysis_outcome"), str)
                    else None
                ),
                agent_tags=self._build_agent_tags(
                    row.agent_tags or [],
                    discovery_source=row.discovery_source,
                    firehose_discovery_mode=row.firehose_discovery_mode,
                ),
                suggested_new_tags=list(row.suggested_new_tags or []),
                monetization_potential=row.monetization_potential,
                has_readme_artifact=bool(row.has_readme_artifact),
                has_analysis_artifact=bool(row.has_analysis_artifact),
                is_starred=bool(row.is_starred),
                user_tags=user_tags_by_repository_id.get(row.github_repository_id, []),
                idea_family_ids=idea_family_ids_by_repository_id.get(row.github_repository_id, []),
                scout_context=scout_context_by_repository_id.get(row.github_repository_id),
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

    def _fetch_scout_context(self, github_repository_id: int) -> ScoutDiscoveryRecord | None:
        row = self.session.exec(
            select(
                IdeaSearchDiscovery.idea_search_id,
                IdeaSearchDiscovery.query_index,
                IdeaSearchDiscovery.query_text,
                IdeaSearchDiscovery.discovered_at,
                IdeaSearch.idea_text,
            )
            .join(IdeaSearch, IdeaSearchDiscovery.idea_search_id == IdeaSearch.id)
            .where(IdeaSearchDiscovery.github_repository_id == github_repository_id)
        ).first()
        if row is None:
            return None
        return ScoutDiscoveryRecord(
            idea_search_id=row.idea_search_id,
            idea_text=row.idea_text,
            query_index=row.query_index,
            query_text=row.query_text,
            discovered_at=row.discovered_at,
        )

    @staticmethod
    def _build_failure_context(intake: RepositoryIntake) -> RepositoryFailureContextRecord | None:
        return RepositoryExplorationRepository._build_catalog_failure_context(
            intake_status=intake.queue_status,
            analysis_status=intake.analysis_status,
            discovery_source=intake.discovery_source,
            analysis_failure_code=(
                intake.analysis_failure_code.value
                if intake.analysis_failure_code is not None
                else None
            ),
            analysis_failure_message=intake.analysis_failure_message,
            intake_failed_at=intake.last_failed_at,
            analysis_failed_at=intake.analysis_last_failed_at,
        )

    @staticmethod
    def _build_catalog_failure_context(
        *,
        intake_status: RepositoryQueueStatus,
        analysis_status: RepositoryAnalysisStatus,
        discovery_source: RepositoryDiscoverySource,
        analysis_failure_code: str | None,
        analysis_failure_message: str | None,
        intake_failed_at: datetime | None,
        analysis_failed_at: datetime | None,
    ) -> RepositoryFailureContextRecord | None:
        if analysis_status is RepositoryAnalysisStatus.FAILED:
            return RepositoryFailureContextRecord(
                stage="analysis",
                step="analysis",
                upstream_source=discovery_source.value,
                error_code=analysis_failure_code,
                error_message=(
                    analysis_failure_message
                    or "Analysis failed without a recorded error message."
                ),
                failed_at=analysis_failed_at,
            )

        if intake_status is RepositoryQueueStatus.FAILED:
            return RepositoryFailureContextRecord(
                stage="intake",
                step="repository_intake",
                upstream_source=discovery_source.value,
                error_code=None,
                error_message="Repository intake failed before triage or analysis completed.",
                failed_at=intake_failed_at,
            )

        return None

    @staticmethod
    def _build_agent_tags(
        analysis_tags: list[str] | tuple[str, ...] | None,
        *,
        discovery_source: RepositoryDiscoverySource,
        firehose_discovery_mode: RepositoryFirehoseMode | None,
    ) -> list[str]:
        tags = [str(tag) for tag in (analysis_tags or [])]
        seen = {tag.lower() for tag in tags}

        if (
            discovery_source is RepositoryDiscoverySource.IDEA_SCOUT
            and "idea_scout" not in seen
        ):
            tags.insert(0, "idea_scout")
            seen.add("idea_scout")

        if (
            discovery_source is RepositoryDiscoverySource.FIREHOSE
            and firehose_discovery_mode is not None
            and firehose_discovery_mode.value not in seen
        ):
            tags.insert(0, firehose_discovery_mode.value)

        return tags

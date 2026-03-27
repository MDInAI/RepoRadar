from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models import (
    RepositoryAnalysisStatus,
    RepositoryArtifactKind,
    RepositoryCategory,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryMonetizationPotential,
    RepositoryQueueStatus,
    RepositoryTriageExplanationKind,
    RepositoryTriageStatus,
)


class RepositoryArtifactRefResponse(BaseModel):
    artifact_kind: RepositoryArtifactKind
    runtime_relative_path: str
    content_sha256: str
    byte_size: int
    content_type: str
    source_kind: str
    source_url: str | None = None
    provenance_metadata: dict[str, object] = Field(default_factory=dict)
    generated_at: datetime


class RepositoryAnalysisSummaryResponse(BaseModel):
    monetization_potential: RepositoryMonetizationPotential
    category: RepositoryCategory | None = None
    category_confidence_score: int | None = None
    analysis_mode: str | None = None
    analysis_outcome: str | None = None
    analysis_schema_version: str | None = None
    analysis_evidence_version: str | None = None
    insufficient_evidence_reason: str | None = None
    evidence_summary: str | None = None
    analysis_signals: dict[str, object] = Field(default_factory=dict)
    score_breakdown: dict[str, int] = Field(default_factory=dict)
    analysis_summary_short: str | None = None
    analysis_summary_long: str | None = None
    supporting_signals: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    agent_tags: list[str] = Field(default_factory=list)
    suggested_new_categories: list[str] = Field(default_factory=list)
    suggested_new_tags: list[str] = Field(default_factory=list)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    missing_feature_signals: list[str] = Field(default_factory=list)
    problem_statement: str | None = None
    target_customer: str | None = None
    product_type: str | None = None
    business_model_guess: str | None = None
    technical_stack: str | None = None
    target_audience: str | None = None
    open_problems: str | None = None
    competitors: str | None = None
    confidence_score: int | None = None
    recommended_action: str | None = None
    source_metadata: dict[str, object] = Field(default_factory=dict)
    analyzed_at: datetime


class RepositoryTriageExplanationResponse(BaseModel):
    kind: RepositoryTriageExplanationKind
    summary: str
    matched_include_rules: list[str] = Field(default_factory=list)
    matched_exclude_rules: list[str] = Field(default_factory=list)
    explained_at: datetime


class RepositoryTriageContextResponse(BaseModel):
    triage_status: RepositoryTriageStatus
    triaged_at: datetime | None = None
    explanation: RepositoryTriageExplanationResponse | None = None


class RepositoryReadmeSnapshotResponse(BaseModel):
    artifact: RepositoryArtifactRefResponse | None = None
    content: str | None = None
    normalization_version: str | None = None
    raw_character_count: int | None = None
    normalized_character_count: int | None = None
    removed_line_count: int | None = None


class RepositoryAnalysisArtifactResponse(BaseModel):
    artifact: RepositoryArtifactRefResponse | None = None
    provider_name: str | None = None
    model_name: str | None = None
    source_metadata: dict[str, object] = Field(default_factory=dict)
    payload: dict[str, object] | None = None


class RepositoryFailureContextResponse(BaseModel):
    stage: str
    step: str
    upstream_source: str
    error_code: str | None = None
    error_message: str | None = None
    failed_at: datetime | None = None


class RepositoryProcessingContextResponse(BaseModel):
    intake_created_at: datetime | None = None
    intake_started_at: datetime | None = None
    intake_completed_at: datetime | None = None
    intake_failed_at: datetime | None = None
    triaged_at: datetime | None = None
    analysis_started_at: datetime | None = None
    analysis_completed_at: datetime | None = None
    analysis_last_attempted_at: datetime | None = None
    analysis_failed_at: datetime | None = None
    failure: RepositoryFailureContextResponse | None = None


class RepositoryExplorationResponse(BaseModel):
    github_repository_id: int
    source_provider: str
    owner_login: str
    repository_name: str
    full_name: str
    repository_description: str | None = None
    discovery_source: RepositoryDiscoverySource
    firehose_discovery_mode: RepositoryFirehoseMode | None = None
    intake_status: RepositoryQueueStatus
    triage_status: RepositoryTriageStatus
    analysis_status: RepositoryAnalysisStatus
    stargazers_count: int
    forks_count: int
    github_created_at: datetime | None = None
    discovered_at: datetime
    status_updated_at: datetime
    pushed_at: datetime | None = None
    category: RepositoryCategory | None = None
    agent_tags: list[str] = Field(default_factory=list)
    triage: RepositoryTriageContextResponse
    analysis_summary: RepositoryAnalysisSummaryResponse | None = None
    readme_snapshot: RepositoryReadmeSnapshotResponse | None = None
    analysis_artifact: RepositoryAnalysisArtifactResponse | None = None
    artifacts: list[RepositoryArtifactRefResponse] = Field(default_factory=list)
    processing: RepositoryProcessingContextResponse
    has_readme_artifact: bool = False
    has_analysis_artifact: bool = False
    is_starred: bool = False
    user_tags: list[str] = Field(default_factory=list)
    idea_family_ids: list[int] = Field(default_factory=list)


class RepositoryCatalogSortBy(StrEnum):
    STARS = "stars"
    FORKS = "forks"
    PUSHED_AT = "pushed_at"
    INGESTED_AT = "ingested_at"


class RepositoryCatalogSortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class RepositoryCatalogQueryParams(BaseModel):
    page: int = 1
    page_size: int = 30
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
    sort_by: RepositoryCatalogSortBy = RepositoryCatalogSortBy.STARS
    sort_order: RepositoryCatalogSortOrder = RepositoryCatalogSortOrder.DESC


class RepositoryCatalogItemResponse(BaseModel):
    github_repository_id: int
    full_name: str
    owner_login: str
    repository_name: str
    repository_description: str | None = None
    stargazers_count: int
    forks_count: int
    pushed_at: datetime | None = None
    discovery_source: RepositoryDiscoverySource
    firehose_discovery_mode: RepositoryFirehoseMode | None = None
    intake_status: RepositoryQueueStatus
    triage_status: RepositoryTriageStatus
    analysis_status: RepositoryAnalysisStatus
    queue_created_at: datetime | None = None
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    intake_failed_at: datetime | None = None
    analysis_failed_at: datetime | None = None
    failure: RepositoryFailureContextResponse | None = None
    category: RepositoryCategory | None = None
    category_confidence_score: int | None = None
    confidence_score: int | None = None
    analysis_outcome: str | None = None
    agent_tags: list[str] = Field(default_factory=list)
    suggested_new_tags: list[str] = Field(default_factory=list)
    monetization_potential: RepositoryMonetizationPotential | None = None
    has_readme_artifact: bool = False
    has_analysis_artifact: bool = False
    is_starred: bool = False
    user_tags: list[str] = Field(default_factory=list)
    idea_family_ids: list[int] = Field(default_factory=list)


class RepositoryCatalogPageResponse(BaseModel):
    items: list[RepositoryCatalogItemResponse] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    total_pages: int


class RepositoryProcessingQueueSummaryResponse(BaseModel):
    pending: int = 0
    in_progress: int = 0
    completed: int = 0
    failed: int = 0


class RepositoryProcessingTriageSummaryResponse(BaseModel):
    pending: int = 0
    accepted: int = 0
    rejected: int = 0


class RepositoryProcessingAnalysisSummaryResponse(BaseModel):
    pending: int = 0
    in_progress: int = 0
    completed: int = 0
    failed: int = 0


class RepositoryBacklogSummaryResponse(BaseModel):
    queue: RepositoryProcessingQueueSummaryResponse
    triage: RepositoryProcessingTriageSummaryResponse
    analysis: RepositoryProcessingAnalysisSummaryResponse

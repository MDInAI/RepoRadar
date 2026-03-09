from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models import (
    RepositoryAnalysisStatus,
    RepositoryArtifactKind,
    RepositoryDiscoverySource,
    RepositoryMonetizationPotential,
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
    generated_at: datetime


class RepositoryAnalysisSummaryResponse(BaseModel):
    monetization_potential: RepositoryMonetizationPotential
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    missing_feature_signals: list[str] = Field(default_factory=list)
    analyzed_at: datetime


class RepositoryExplorationResponse(BaseModel):
    github_repository_id: int
    full_name: str
    repository_description: str | None = None
    discovery_source: RepositoryDiscoverySource
    triage_status: RepositoryTriageStatus
    analysis_status: RepositoryAnalysisStatus
    stargazers_count: int
    forks_count: int
    pushed_at: datetime | None = None
    analysis_summary: RepositoryAnalysisSummaryResponse | None = None
    artifacts: list[RepositoryArtifactRefResponse] = Field(default_factory=list)
    has_readme_artifact: bool = False
    has_analysis_artifact: bool = False


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
    triage_status: RepositoryTriageStatus | None = None
    analysis_status: RepositoryAnalysisStatus | None = None
    monetization_potential: RepositoryMonetizationPotential | None = None
    min_stars: int | None = None
    max_stars: int | None = None
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
    triage_status: RepositoryTriageStatus
    analysis_status: RepositoryAnalysisStatus
    monetization_potential: RepositoryMonetizationPotential | None = None
    has_readme_artifact: bool = False
    has_analysis_artifact: bool = False


class RepositoryCatalogPageResponse(BaseModel):
    items: list[RepositoryCatalogItemResponse] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    total_pages: int

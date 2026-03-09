from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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


class RepositoryExplorationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_repository_exploration(self, github_repository_id: int) -> RepositoryExplorationRecord | None:
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

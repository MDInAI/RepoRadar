from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, select

from app.repositories.repository_artifact_payload_repository import (
    RepositoryArtifactPayloadRepository,
)
from agentic_workers.core.config import settings
from agentic_workers.providers.readme_analyst import LLMReadmeBusinessAnalysis, ReadmeBusinessAnalysis
from agentic_workers.storage.artifact_store import (
    RepositoryArtifactPayload,
    activate_repository_artifacts,
    build_json_artifact,
)
from agentic_workers.storage.backend_models import (
    RepositoryCategory,
    RepositoryAnalysisFailureCode,
    RepositoryAnalysisResult,
    RepositoryAnalysisStatus,
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryIntake,
    RepositoryMonetizationPotential,
)
from agentic_workers.storage.readme_store import build_readme_artifact

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PersistedAnalysisArtifacts:
    readme_artifact: RepositoryArtifactPayload
    analysis_artifact: RepositoryArtifactPayload


def list_pending_analysis_targets(session: Session) -> list[RepositoryIntake]:
    from agentic_workers.storage.backend_models import RepositoryTriageStatus

    return session.exec(
        select(RepositoryIntake)
        .where(RepositoryIntake.triage_status == RepositoryTriageStatus.ACCEPTED)
        .where(RepositoryIntake.analysis_status != RepositoryAnalysisStatus.COMPLETED)
        .order_by(RepositoryIntake.triaged_at, RepositoryIntake.github_repository_id)
    ).all()


def mark_analysis_in_progress(
    session: Session,
    *,
    repository: RepositoryIntake,
    started_at: datetime,
) -> None:
    repository.analysis_status = RepositoryAnalysisStatus.IN_PROGRESS
    repository.analysis_started_at = started_at
    repository.analysis_last_attempted_at = started_at
    repository.analysis_failure_code = None
    repository.analysis_failure_message = None
    session.add(repository)
    session.commit()


def persist_analysis_success(
    session: Session,
    *,
    repository_id: int,
    repository_full_name: str,
    runtime_dir: Path | None,
    normalized_readme: str,
    readme_source_url: str,
    readme_fetched_at: datetime,
    normalization_version: str,
    raw_character_count: int,
    normalized_character_count: int,
    removed_line_count: int,
    analysis: LLMReadmeBusinessAnalysis,
    analysis_provider_name: str,
    completed_at: datetime,
) -> PersistedAnalysisArtifacts:
    repository = session.get(RepositoryIntake, repository_id)
    if repository is None:
        raise RuntimeError(
            f"repository row could not be reloaded for github_repository_id={repository_id}"
        )

    readme_artifact = build_readme_artifact(
        github_repository_id=repository_id,
        content=normalized_readme,
        source_url=readme_source_url,
        normalization_version=normalization_version,
        raw_character_count=raw_character_count,
        normalized_character_count=normalized_character_count,
        removed_line_count=removed_line_count,
        generated_at=completed_at,
    )
    analysis_artifact = build_json_artifact(
        runtime_relative_path=f"data/analyses/{repository_id}.json",
        artifact_kind=RepositoryArtifactKind.ANALYSIS_RESULT,
        payload={
            "schema_version": "story-3.4-v1",
            "github_repository_id": repository_id,
            "full_name": repository_full_name,
            "generated_at": completed_at.isoformat(),
            "source": {
                "kind": "repository_readme",
                "url": readme_source_url,
                "fetched_at": readme_fetched_at.isoformat(),
                "readme_artifact_path": readme_artifact.runtime_relative_path,
                "readme_artifact_sha256": readme_artifact.content_sha256,
            },
            "analysis_provider": analysis_provider_name,
            "analysis": analysis.model_dump(mode="json"),
        },
        source_kind="repository_analysis",
        source_url=readme_source_url,
        provenance_metadata={
            "analysis_provider": analysis_provider_name,
            "source_kind": "repository_readme",
        },
        generated_at=completed_at,
    )

    artifact_payload_repository = RepositoryArtifactPayloadRepository(
        session,
        runtime_dir=runtime_dir,
    )
    try:
        repository.analysis_status = RepositoryAnalysisStatus.COMPLETED
        repository.analysis_completed_at = completed_at
        repository.analysis_last_attempted_at = completed_at
        repository.analysis_last_failed_at = None
        repository.analysis_failure_code = None
        repository.analysis_failure_message = None
        session.add(repository)

        _upsert_analysis_result(
            session,
            repository_id=repository_id,
            analysis=analysis,
            source_metadata={
                "endpoint": readme_source_url,
                "fetched_at": readme_fetched_at.isoformat(),
                "normalization_version": normalization_version,
                "raw_character_count": raw_character_count,
                "normalized_character_count": normalized_character_count,
                "removed_line_count": removed_line_count,
                "readme_artifact_path": readme_artifact.runtime_relative_path,
                "readme_artifact_sha256": readme_artifact.content_sha256,
                "analysis_artifact_path": analysis_artifact.runtime_relative_path,
                "analysis_artifact_sha256": analysis_artifact.content_sha256,
                "analysis_provider": analysis_provider_name,
            },
            analyzed_at=completed_at,
        )
        _upsert_repository_artifacts(
            session,
            repository_id=repository_id,
            artifacts=[readme_artifact, analysis_artifact],
        )
        _upsert_repository_artifact_payloads(
            artifact_payload_repository,
            repository_id=repository_id,
            artifacts=[readme_artifact, analysis_artifact],
        )
        session.commit()
    except Exception:
        _rollback_after_failure(session)
        raise

    if settings.ARTIFACT_DEBUG_MIRROR and runtime_dir is not None:
        try:
            activate_repository_artifacts(
                runtime_dir=runtime_dir,
                artifacts=[readme_artifact, analysis_artifact],
            )
        except Exception as exc:
            logger.warning(
                "Artifact mirror write failed for repository %s: %s",
                repository_id,
                exc,
            )

    return PersistedAnalysisArtifacts(
        readme_artifact=readme_artifact,
        analysis_artifact=analysis_artifact,
    )


def persist_analysis_failure(
    session: Session,
    *,
    repository_id: int,
    failure_code: RepositoryAnalysisFailureCode,
    message: str,
    failed_at: datetime,
    started_at: datetime,
    commit: bool = True,
) -> None:
    repository = session.get(RepositoryIntake, repository_id)
    if repository is None:
        raise RuntimeError(
            f"failure status update skipped: repository row could not be reloaded for {repository_id}"
        )

    repository.analysis_status = RepositoryAnalysisStatus.FAILED
    repository.analysis_started_at = started_at
    repository.analysis_completed_at = None
    repository.analysis_last_attempted_at = failed_at
    repository.analysis_last_failed_at = failed_at
    repository.analysis_failure_code = failure_code
    repository.analysis_failure_message = message
    session.add(repository)
    if commit:
        session.commit()


def _upsert_analysis_result(
    session: Session,
    *,
    repository_id: int,
    analysis: LLMReadmeBusinessAnalysis,
    source_metadata: dict[str, object],
    analyzed_at: datetime,
) -> None:
    values = {
        "github_repository_id": repository_id,
        "source_provider": "github",
        "source_kind": "repository_readme",
        "source_metadata": source_metadata,
        "monetization_potential": analysis.monetization_potential.value if hasattr(analysis, 'monetization_potential') else None,
        "category": analysis.category,
        "category_confidence_score": analysis.category_confidence_score,
        "agent_tags": list(analysis.agent_tags),
        "pros": list(analysis.pros) if hasattr(analysis, 'pros') else [],
        "cons": list(analysis.cons) if hasattr(analysis, 'cons') else [],
        "missing_feature_signals": list(analysis.missing_feature_signals) if hasattr(analysis, 'missing_feature_signals') else [],
        "problem_statement": analysis.problem_statement,
        "target_customer": analysis.target_customer,
        "product_type": analysis.product_type,
        "business_model_guess": analysis.business_model_guess,
        "technical_stack": analysis.technical_stack,
        "target_audience": analysis.target_audience,
        "open_problems": analysis.open_problems,
        "competitors": analysis.competitors,
        "analyzed_at": analyzed_at,
    }
    update_values = {key: value for key, value in values.items() if key != "github_repository_id"}
    table = RepositoryAnalysisResult.__table__
    dialect_name = session.get_bind().dialect.name

    if dialect_name == "sqlite":
        statement = sqlite_insert(table).values(**values)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[table.c.github_repository_id],
                set_=update_values,
            )
        )
        return

    if dialect_name == "postgresql":
        statement = postgresql_insert(table).values(**values)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[table.c.github_repository_id],
                set_=update_values,
            )
        )
        return

    result = session.get(RepositoryAnalysisResult, repository_id)
    if result is None:
        result = RepositoryAnalysisResult(**values)
    else:
        result.source_provider = "github"
        result.source_kind = "repository_readme"
        result.source_metadata = source_metadata
        result.monetization_potential = RepositoryMonetizationPotential(
            analysis.monetization_potential.value
        )
        result.category = (
            RepositoryCategory(analysis.category) if analysis.category is not None else None
        )
        result.agent_tags = list(analysis.agent_tags)
        result.pros = list(analysis.pros)
        result.cons = list(analysis.cons)
        result.missing_feature_signals = list(analysis.missing_feature_signals)
        result.analyzed_at = analyzed_at
    session.add(result)


def _upsert_repository_artifacts(
    session: Session,
    *,
    repository_id: int,
    artifacts: list[RepositoryArtifactPayload],
) -> None:
    table = RepositoryArtifact.__table__
    dialect_name = session.get_bind().dialect.name

    for artifact in artifacts:
        values = {
            "github_repository_id": repository_id,
            "artifact_kind": artifact.artifact_kind.value,
            "runtime_relative_path": artifact.runtime_relative_path,
            "content_sha256": artifact.content_sha256,
            "byte_size": artifact.byte_size,
            "content_type": artifact.content_type,
            "source_kind": artifact.source_kind,
            "source_url": artifact.source_url,
            "provenance_metadata": artifact.provenance_metadata,
            "generated_at": artifact.generated_at,
        }
        update_values = {
            key: value
            for key, value in values.items()
            if key not in {"github_repository_id", "artifact_kind"}
        }

        if dialect_name == "sqlite":
            statement = sqlite_insert(table).values(**values)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[table.c.github_repository_id, table.c.artifact_kind],
                    set_=update_values,
                )
            )
            continue

        if dialect_name == "postgresql":
            statement = postgresql_insert(table).values(**values)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[table.c.github_repository_id, table.c.artifact_kind],
                    set_=update_values,
                )
            )
            continue

        record = session.get(RepositoryArtifact, (repository_id, artifact.artifact_kind))
        if record is None:
            record = RepositoryArtifact(
                github_repository_id=repository_id,
                artifact_kind=artifact.artifact_kind,
                runtime_relative_path=artifact.runtime_relative_path,
                content_sha256=artifact.content_sha256,
                byte_size=artifact.byte_size,
                content_type=artifact.content_type,
                source_kind=artifact.source_kind,
                source_url=artifact.source_url,
                provenance_metadata=dict(artifact.provenance_metadata),
                generated_at=artifact.generated_at,
            )
        else:
            record.runtime_relative_path = artifact.runtime_relative_path
            record.content_sha256 = artifact.content_sha256
            record.byte_size = artifact.byte_size
            record.content_type = artifact.content_type
            record.source_kind = artifact.source_kind
            record.source_url = artifact.source_url
            record.provenance_metadata = dict(artifact.provenance_metadata)
            record.generated_at = artifact.generated_at
        session.add(record)


def _rollback_after_failure(session: Session) -> str | None:
    try:
        session.rollback()
    except Exception as exc:
        return f"rollback failed: {exc}"
    return None


def _upsert_repository_artifact_payloads(
    artifact_payload_repository: RepositoryArtifactPayloadRepository,
    *,
    repository_id: int,
    artifacts: list[RepositoryArtifactPayload],
) -> None:
    for artifact in artifacts:
        artifact_payload_repository.upsert_text_artifact(
            github_repository_id=repository_id,
            artifact_kind=artifact.artifact_kind,
            content_text=artifact.content_bytes.decode("utf-8"),
            updated_at=artifact.generated_at,
        )

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
from agentic_workers.providers.readme_analyst import LLMReadmeBusinessAnalysis
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

CURRENT_ANALYSIS_SCHEMA_VERSION = "story-3.4-v2"
_REQUIRED_ANALYSIS_METADATA_KEYS = frozenset(
    {
        "analysis_mode",
        "analysis_outcome",
        "analysis_evidence_version",
        "analysis_summary_short",
        "score_breakdown",
    }
)


@dataclass(frozen=True, slots=True)
class PersistedAnalysisArtifacts:
    readme_artifact: RepositoryArtifactPayload | None
    analysis_artifact: RepositoryArtifactPayload


def list_pending_analysis_targets(session: Session) -> list[RepositoryIntake]:
    from agentic_workers.storage.backend_models import RepositoryTriageStatus

    accepted_repositories = session.exec(
        select(RepositoryIntake)
        .where(RepositoryIntake.triage_status == RepositoryTriageStatus.ACCEPTED)
        .order_by(RepositoryIntake.triaged_at, RepositoryIntake.github_repository_id)
    ).all()
    if not accepted_repositories:
        return []

    repository_ids = [repository.github_repository_id for repository in accepted_repositories]
    analysis_rows = session.exec(
        select(RepositoryAnalysisResult).where(
            RepositoryAnalysisResult.github_repository_id.in_(repository_ids)
        )
    ).all()
    analysis_by_repository_id = {
        analysis.github_repository_id: analysis for analysis in analysis_rows
    }

    pending_targets: list[RepositoryIntake] = []
    stale_completed_count = 0
    for repository in accepted_repositories:
        if repository.analysis_status is not RepositoryAnalysisStatus.COMPLETED:
            pending_targets.append(repository)
            continue

        if _analysis_requires_reanalysis(
            analysis_by_repository_id.get(repository.github_repository_id)
        ):
            pending_targets.append(repository)
            stale_completed_count += 1

    if stale_completed_count > 0:
        logger.info(
            "Queued %d accepted repositories for Analyst refresh because they use legacy analysis output",
            stale_completed_count,
        )

    return pending_targets


def _analysis_requires_reanalysis(analysis: RepositoryAnalysisResult | None) -> bool:
    if analysis is None:
        return True

    metadata = analysis.source_metadata
    if not isinstance(metadata, dict):
        return True

    if metadata.get("analysis_schema_version") != CURRENT_ANALYSIS_SCHEMA_VERSION:
        return True

    return any(key not in metadata for key in _REQUIRED_ANALYSIS_METADATA_KEYS)


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
    normalized_readme: str | None,
    readme_source_url: str | None,
    readme_fetched_at: datetime | None,
    normalization_version: str | None,
    raw_character_count: int | None,
    normalized_character_count: int | None,
    removed_line_count: int | None,
    analysis: LLMReadmeBusinessAnalysis,
    analysis_provider_name: str,
    analysis_model_name: str | None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    source_kind: str = "repository_readme",
    analysis_mode: str | None = None,
    analysis_outcome: str | None = None,
    analysis_schema_version: str | None = None,
    analysis_evidence_version: str | None = None,
    insufficient_evidence_reason: str | None = None,
    evidence_summary: str | None = None,
    analysis_signals: dict[str, object] | None = None,
    score_breakdown: dict[str, int] | None = None,
    analysis_summary_short: str | None = None,
    analysis_summary_long: str | None = None,
    supporting_signals: list[str] | None = None,
    red_flags: list[str] | None = None,
    contradictions: list[str] | None = None,
    missing_information: list[str] | None = None,
    completed_at: datetime,
) -> PersistedAnalysisArtifacts:
    repository = session.get(RepositoryIntake, repository_id)
    if repository is None:
        raise RuntimeError(
            f"repository row could not be reloaded for github_repository_id={repository_id}"
        )

    readme_artifact: RepositoryArtifactPayload | None = None
    if (
        normalized_readme is not None
        and readme_source_url is not None
        and readme_fetched_at is not None
        and normalization_version is not None
        and raw_character_count is not None
        and normalized_character_count is not None
        and removed_line_count is not None
    ):
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
            "schema_version": analysis_schema_version or "story-3.4-v1",
            "github_repository_id": repository_id,
            "full_name": repository_full_name,
            "generated_at": completed_at.isoformat(),
            "source": {
                "kind": source_kind,
                "url": readme_source_url,
                "fetched_at": readme_fetched_at.isoformat() if readme_fetched_at is not None else None,
                "readme_artifact_path": (
                    readme_artifact.runtime_relative_path if readme_artifact is not None else None
                ),
                "readme_artifact_sha256": (
                    readme_artifact.content_sha256 if readme_artifact is not None else None
                ),
            },
            "analysis_provider": analysis_provider_name,
            "analysis_model_name": analysis_model_name,
            "analysis_mode": analysis_mode,
            "analysis_outcome": analysis_outcome,
            "analysis_evidence_version": analysis_evidence_version,
            "insufficient_evidence_reason": insufficient_evidence_reason,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "evidence": {
                "summary": evidence_summary,
                "signals": analysis_signals or {},
                "score_breakdown": score_breakdown or {},
                "analysis_summary_short": analysis_summary_short,
                "analysis_summary_long": analysis_summary_long,
                "supporting_signals": supporting_signals or [],
                "red_flags": red_flags or [],
                "contradictions": contradictions or [],
                "missing_information": missing_information or [],
            },
            "analysis": analysis.model_dump(mode="json"),
        },
        source_kind="repository_analysis",
        source_url=readme_source_url,
        provenance_metadata={
            "analysis_provider": analysis_provider_name,
            "analysis_model_name": analysis_model_name,
            "analysis_mode": analysis_mode,
            "analysis_outcome": analysis_outcome,
            "analysis_evidence_version": analysis_evidence_version,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "source_kind": source_kind,
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
            source_kind=source_kind,
            source_metadata={
                "endpoint": readme_source_url,
                "fetched_at": readme_fetched_at.isoformat() if readme_fetched_at is not None else None,
                "normalization_version": normalization_version,
                "raw_character_count": raw_character_count,
                "normalized_character_count": normalized_character_count,
                "removed_line_count": removed_line_count,
                "readme_artifact_path": (
                    readme_artifact.runtime_relative_path if readme_artifact is not None else None
                ),
                "readme_artifact_sha256": (
                    readme_artifact.content_sha256 if readme_artifact is not None else None
                ),
                "analysis_artifact_path": analysis_artifact.runtime_relative_path,
                "analysis_artifact_sha256": analysis_artifact.content_sha256,
                "analysis_provider": analysis_provider_name,
                "analysis_model_name": analysis_model_name,
                "analysis_mode": analysis_mode,
                "analysis_outcome": analysis_outcome,
                "analysis_schema_version": analysis_schema_version,
                "analysis_evidence_version": analysis_evidence_version,
                "insufficient_evidence_reason": insufficient_evidence_reason,
                "evidence_summary": evidence_summary,
                "analysis_signals": analysis_signals or {},
                "score_breakdown": score_breakdown or {},
                "analysis_summary_short": analysis_summary_short,
                "analysis_summary_long": analysis_summary_long,
                "supporting_signals": supporting_signals or [],
                "red_flags": red_flags or [],
                "contradictions": contradictions or [],
                "missing_information": missing_information or [],
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
            analyzed_at=completed_at,
        )
        _upsert_repository_artifacts(
            session,
            repository_id=repository_id,
            artifacts=[artifact for artifact in (readme_artifact, analysis_artifact) if artifact is not None],
        )
        _upsert_repository_artifact_payloads(
            artifact_payload_repository,
            repository_id=repository_id,
            artifacts=[artifact for artifact in (readme_artifact, analysis_artifact) if artifact is not None],
        )
        session.commit()
    except Exception:
        _rollback_after_failure(session)
        raise

    if settings.ARTIFACT_DEBUG_MIRROR and runtime_dir is not None:
        try:
            activate_repository_artifacts(
                runtime_dir=runtime_dir,
                artifacts=[artifact for artifact in (readme_artifact, analysis_artifact) if artifact is not None],
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


def defer_analysis_retry(
    session: Session,
    *,
    repository_id: int,
    failure_code: RepositoryAnalysisFailureCode,
    message: str,
    deferred_at: datetime,
    commit: bool = True,
) -> None:
    repository = session.get(RepositoryIntake, repository_id)
    if repository is None:
        raise RuntimeError(
            f"retry defer skipped: repository row could not be reloaded for {repository_id}"
        )

    repository.analysis_status = RepositoryAnalysisStatus.PENDING
    repository.analysis_started_at = None
    repository.analysis_completed_at = None
    repository.analysis_last_attempted_at = deferred_at
    repository.analysis_last_failed_at = deferred_at
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
    source_kind: str,
    source_metadata: dict[str, object],
    analyzed_at: datetime,
) -> None:
    values = {
        "github_repository_id": repository_id,
        "source_provider": "github",
        "source_kind": source_kind,
        "source_metadata": source_metadata,
        "monetization_potential": analysis.monetization_potential.value if hasattr(analysis, 'monetization_potential') else None,
        "category": analysis.category,
        "category_confidence_score": analysis.category_confidence_score,
        "agent_tags": list(analysis.agent_tags),
        "suggested_new_categories": list(analysis.suggested_new_categories),
        "suggested_new_tags": list(analysis.suggested_new_tags),
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
        "confidence_score": analysis.confidence_score,
        "recommended_action": analysis.recommended_action,
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
        result = RepositoryAnalysisResult(
            github_repository_id=repository_id,
            source_provider="github",
            source_kind=source_kind,
            source_metadata=source_metadata,
            monetization_potential=RepositoryMonetizationPotential(
                analysis.monetization_potential.value
            ),
            category=(
                RepositoryCategory(analysis.category) if analysis.category is not None else None
            ),
            category_confidence_score=analysis.category_confidence_score,
            agent_tags=list(analysis.agent_tags),
            suggested_new_categories=list(analysis.suggested_new_categories),
            suggested_new_tags=list(analysis.suggested_new_tags),
            pros=list(analysis.pros),
            cons=list(analysis.cons),
            missing_feature_signals=list(analysis.missing_feature_signals),
            problem_statement=analysis.problem_statement,
            target_customer=analysis.target_customer,
            product_type=analysis.product_type,
            business_model_guess=analysis.business_model_guess,
            technical_stack=analysis.technical_stack,
            target_audience=analysis.target_audience,
            open_problems=analysis.open_problems,
            competitors=analysis.competitors,
            confidence_score=analysis.confidence_score,
            recommended_action=analysis.recommended_action,
            analyzed_at=analyzed_at,
        )
    else:
        result.source_provider = "github"
        result.source_kind = source_kind
        result.source_metadata = source_metadata
        result.monetization_potential = RepositoryMonetizationPotential(
            analysis.monetization_potential.value
        )
        result.category = (
            RepositoryCategory(analysis.category) if analysis.category is not None else None
        )
        result.category_confidence_score = analysis.category_confidence_score
        result.agent_tags = list(analysis.agent_tags)
        result.suggested_new_categories = list(analysis.suggested_new_categories)
        result.suggested_new_tags = list(analysis.suggested_new_tags)
        result.pros = list(analysis.pros)
        result.cons = list(analysis.cons)
        result.missing_feature_signals = list(analysis.missing_feature_signals)
        result.problem_statement = analysis.problem_statement
        result.target_customer = analysis.target_customer
        result.product_type = analysis.product_type
        result.business_model_guess = analysis.business_model_guess
        result.technical_stack = analysis.technical_stack
        result.target_audience = analysis.target_audience
        result.open_problems = analysis.open_problems
        result.competitors = analysis.competitors
        result.confidence_score = analysis.confidence_score
        result.recommended_action = analysis.recommended_action
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

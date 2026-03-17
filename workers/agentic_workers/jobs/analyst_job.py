from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
import logging
from pathlib import Path
from typing import Callable

from pydantic import ValidationError
from sqlmodel import Session

from agentic_workers.core.events import emit_failure_event
from agentic_workers.core.failure_detector import (
    classify_github_error,
    classify_llm_error,
    determine_severity,
)
from agentic_workers.core.pause_manager import execute_pause, is_agent_paused
from agentic_workers.core.pause_policy import evaluate_pause_policy
from agentic_workers.providers.github_provider import (
    GitHubPayloadError,
    GitHubProviderError,
    GitHubRateLimitError,
    GitHubReadmeNotFoundError,
    GitHubFirehoseProvider,
)
from agentic_workers.providers.repository_evidence import (
    build_insufficient_evidence_analysis,
    determine_analysis_outcome,
    extract_repository_analysis_evidence,
)
from agentic_workers.providers.readme_analyst import (
    LLMReadmeBusinessAnalysis,
    NormalizedReadme,
    ReadmeAnalysisProvider,
    create_analysis_provider,
    normalize_readme,
)
from agentic_workers.storage.agent_progress_snapshots import (
    clear_agent_progress_snapshot,
    write_agent_progress_snapshot,
)
from agentic_workers.storage.analysis_store import (
    CURRENT_ANALYSIS_SCHEMA_VERSION,
    defer_analysis_retry,
    list_pending_analysis_targets,
    mark_analysis_in_progress,
    persist_analysis_failure,
    persist_analysis_success,
)
from agentic_workers.storage.backend_models import (
    FailureClassification,
    FailureSeverity,
    RepositoryAnalysisFailureCode,
    RepositoryAnalysisStatus,
)

logger = logging.getLogger(__name__)

_SELECTED_EVIDENCE_FILES = (
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Dockerfile",
    "docker-compose.yml",
)


class AnalystRunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"
    SKIPPED = "skipped"
    SKIPPED_PAUSED = "skipped_paused"


@dataclass(frozen=True, slots=True)
class AnalystRepositoryOutcome:
    github_repository_id: int
    full_name: str
    analysis_status: RepositoryAnalysisStatus
    failure_code: RepositoryAnalysisFailureCode | None
    failure_message: str | None
    monetization_potential: str | None
    runtime_readme_artifact_path: str | None
    runtime_analysis_artifact_path: str | None
    artifact_error: str | None = None


@dataclass(frozen=True, slots=True)
class AnalystRunResult:
    status: AnalystRunStatus
    outcomes: list[AnalystRepositoryOutcome]
    artifact_path: Path | None
    artifact_error: str | None = None
    provider_name: str | None = None
    model_name: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


ArtifactWriter = Callable[..., Path | None]


def run_analyst_job(
    *,
    session: Session,
    provider: GitHubFirehoseProvider,
    runtime_dir: Path | None,
    analysis_provider: ReadmeAnalysisProvider | None = None,
    should_stop: Callable[[], bool] | None = None,
    write_artifact: ArtifactWriter | None = None,
    agent_run_id: int | None = None,
) -> AnalystRunResult:
    # Check if agent is paused
    if is_agent_paused(session, "analyst"):
        clear_agent_progress_snapshot(runtime_dir=runtime_dir, agent_name="analyst")
        logger.info("Analyst is paused, skipping run")
        return AnalystRunResult(
            status=AnalystRunStatus.SKIPPED_PAUSED,
            outcomes=[],
            artifact_path=None,
        )

    effective_analysis_provider = analysis_provider
    if effective_analysis_provider is None:
        from agentic_workers.core.config import settings
        api_key = settings.ANTHROPIC_API_KEY.get_secret_value() if settings.ANTHROPIC_API_KEY else None
        gemini_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None
        effective_analysis_provider = create_analysis_provider(
            settings.ANALYST_PROVIDER,
            api_key,
            settings.ANALYST_MODEL_NAME,
            gemini_key,
            settings.gemini_api_key_values,
            settings.GEMINI_BASE_URL,
            settings.GEMINI_MODEL_NAME,
            runtime_dir,
        )
    provider_name = getattr(effective_analysis_provider, "provider_name", None)
    model_name = getattr(effective_analysis_provider, "model_name", None)
    artifact_writer = write_artifact or _write_run_artifact

    targets = list_pending_analysis_targets(session)
    total_targets = len(targets)
    outcomes: list[AnalystRepositoryOutcome] = []
    interrupted = False
    stopped_for_rate_limit = False
    consecutive_failures = 0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    _write_analyst_progress_snapshot(
        runtime_dir=runtime_dir,
        provider_name=provider_name,
        total_targets=total_targets,
        outcomes=outcomes,
        current_target=targets[0].full_name if targets else None,
        current_activity="Preparing accepted repositories for analysis.",
    )

    for repository in targets:
        if should_stop is not None and should_stop():
            interrupted = True
            break
        if is_agent_paused(session, "analyst"):
            interrupted = True
            logger.info("Analyst pause detected during run; stopping before next repository.")
            break

        _write_analyst_progress_snapshot(
            runtime_dir=runtime_dir,
            provider_name=provider_name,
            total_targets=total_targets,
            outcomes=outcomes,
            current_target=repository.full_name,
            current_activity="Analyzing accepted repositories.",
        )

        started_at = datetime.now(timezone.utc)
        readme_artifact_path: str | None = None
        analysis_artifact_path: str | None = None
        try:
            mark_analysis_in_progress(session, repository=repository, started_at=started_at)

            readme = None
            normalized: NormalizedReadme | None = None
            readme_source_url: str | None = None
            readme_fetched_at: datetime | None = None
            readme_missing_reason: str | None = None
            repository_input_tokens = 0
            repository_output_tokens = 0
            repository_total_tokens = 0

            try:
                readme = provider.get_readme(
                    owner_login=repository.owner_login,
                    repository_name=repository.repository_name,
                )
                normalized = normalize_readme(readme.content)
                readme_source_url = readme.source_url
                readme_fetched_at = readme.fetched_at
                if not normalized.normalized_text:
                    readme_missing_reason = "README content was empty after normalization."
                    normalized = None
            except GitHubReadmeNotFoundError as exc:
                readme_missing_reason = str(exc)

            evidence = extract_repository_analysis_evidence(
                repository=repository,
                normalized_readme=normalized,
                observed_at=started_at,
                repository_intelligence=_gather_repository_intelligence(
                    provider=provider,
                    owner_login=repository.owner_login,
                    repository_name=repository.repository_name,
                ),
                readme_missing_reason=readme_missing_reason,
            )
            analysis_mode = "fast"

            if normalized is None:
                analysis = build_insufficient_evidence_analysis(
                    repository=repository,
                    evidence=evidence,
                )
            else:
                try:
                    raw_analysis = effective_analysis_provider.analyze(
                        repository_full_name=repository.full_name,
                        readme=normalized,
                        evidence={
                            **evidence.to_prompt_payload(),
                            "analysis_mode_target": "fast",
                        },
                    )
                    usage = getattr(effective_analysis_provider, "last_usage", None)
                    repository_input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
                    repository_output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
                    repository_total_tokens = int(
                        getattr(usage, "total_tokens", repository_input_tokens + repository_output_tokens)
                        or 0
                    )
                except Exception as exc:
                    consecutive_failures += 1
                    classification = classify_llm_error(exc)
                    failure_code = _analysis_failure_code_for_llm(classification)
                    recovery_error = _record_failure(
                        session=session,
                        repository_id=repository.github_repository_id,
                        failure_code=failure_code,
                        message=str(exc),
                        failed_at=datetime.now(timezone.utc),
                        started_at=started_at,
                        commit=True,
                    )
                    failure_message = _join_messages(str(exc), recovery_error) or str(exc)
                    outcomes.append(
                        AnalystRepositoryOutcome(
                            github_repository_id=repository.github_repository_id,
                            full_name=repository.full_name,
                            analysis_status=RepositoryAnalysisStatus.FAILED,
                            failure_code=failure_code,
                            failure_message=failure_message,
                            monetization_potential=None,
                            runtime_readme_artifact_path=readme_artifact_path,
                            runtime_analysis_artifact_path=analysis_artifact_path,
                        )
                    )
                    if recovery_error is None:
                        _emit_analysis_failure_event(
                            session,
                            agent_run_id=agent_run_id,
                            repository_id=repository.github_repository_id,
                            full_name=repository.full_name,
                            failure_code=failure_code,
                            message=failure_message,
                            classification=classification,
                            failure_severity=determine_severity(
                                classification,
                                consecutive_failures,
                            ),
                            consecutive_failures=consecutive_failures,
                            upstream_provider="llm",
                            http_status_code=_extract_http_status_code(exc),
                            retry_after_seconds=_extract_retry_after_seconds(exc),
                        )
                        session.commit()
                    continue
                analysis = LLMReadmeBusinessAnalysis.model_validate_json(raw_analysis)
                if _should_run_deep_analysis(repository=repository, evidence=evidence, analysis=analysis):
                    raw_deep_analysis = effective_analysis_provider.analyze(
                        repository_full_name=repository.full_name,
                        readme=normalized,
                        evidence={
                            **evidence.to_prompt_payload(),
                            "analysis_mode_target": "deep",
                            "fast_analysis": analysis.model_dump(mode="json"),
                        },
                    )
                    deep_usage = getattr(effective_analysis_provider, "last_usage", None)
                    repository_input_tokens += int(getattr(deep_usage, "input_tokens", 0) or 0)
                    repository_output_tokens += int(getattr(deep_usage, "output_tokens", 0) or 0)
                    repository_total_tokens += int(
                        getattr(
                            deep_usage,
                            "total_tokens",
                            int(getattr(deep_usage, "input_tokens", 0) or 0)
                            + int(getattr(deep_usage, "output_tokens", 0) or 0),
                        )
                        or 0
                    )
                    analysis = LLMReadmeBusinessAnalysis.model_validate_json(raw_deep_analysis)
                    analysis_mode = "deep"

            analysis_outcome = determine_analysis_outcome(
                analysis=analysis,
                evidence=evidence,
            )
            completed_at = datetime.now(timezone.utc)

            persisted = persist_analysis_success(
                session,
                repository_id=repository.github_repository_id,
                repository_full_name=repository.full_name,
                runtime_dir=runtime_dir,
                normalized_readme=normalized.normalized_text if normalized is not None else None,
                readme_source_url=readme_source_url,
                readme_fetched_at=readme_fetched_at,
                normalization_version="story-3.4-v1" if normalized is not None else None,
                raw_character_count=normalized.raw_character_count if normalized is not None else None,
                normalized_character_count=(
                    normalized.normalized_character_count if normalized is not None else None
                ),
                removed_line_count=normalized.removed_line_count if normalized is not None else None,
                analysis=analysis,
                analysis_provider_name=provider_name or effective_analysis_provider.__class__.__name__,
                analysis_model_name=model_name,
                input_tokens=repository_input_tokens,
                output_tokens=repository_output_tokens,
                total_tokens=repository_total_tokens,
                source_kind="repository_readme" if normalized is not None else "repository_evidence",
                analysis_mode=analysis_mode,
                analysis_outcome=analysis_outcome,
                analysis_schema_version=CURRENT_ANALYSIS_SCHEMA_VERSION,
                analysis_evidence_version=evidence.evidence_version,
                insufficient_evidence_reason=evidence.insufficient_evidence_reason,
                evidence_summary=evidence.evidence_summary,
                analysis_signals=evidence.signals,
                score_breakdown=evidence.score_breakdown,
                analysis_summary_short=evidence.analysis_summary_short,
                analysis_summary_long=evidence.analysis_summary_long,
                supporting_signals=evidence.supporting_signals,
                red_flags=[
                    *evidence.red_flags,
                    *evidence.contradictions,
                    *evidence.missing_information,
                ],
                contradictions=evidence.contradictions,
                missing_information=evidence.missing_information,
                completed_at=completed_at,
            )
            readme_artifact_path = (
                persisted.readme_artifact.runtime_relative_path
                if persisted.readme_artifact is not None
                else None
            )
            analysis_artifact_path = persisted.analysis_artifact.runtime_relative_path
            input_tokens += repository_input_tokens
            output_tokens += repository_output_tokens
            total_tokens += repository_total_tokens
            consecutive_failures = 0
            outcomes.append(
                AnalystRepositoryOutcome(
                    github_repository_id=repository.github_repository_id,
                    full_name=repository.full_name,
                    analysis_status=RepositoryAnalysisStatus.COMPLETED,
                    failure_code=None,
                    failure_message=None,
                    monetization_potential=analysis.monetization_potential.value,
                    runtime_readme_artifact_path=readme_artifact_path,
                    runtime_analysis_artifact_path=analysis_artifact_path,
                )
            )
            _write_analyst_progress_snapshot(
                runtime_dir=runtime_dir,
                provider_name=provider_name,
                total_targets=total_targets,
                outcomes=outcomes,
                current_target=repository.full_name,
                current_activity="Persisted repository analysis.",
            )
        except _AnalystFailure as exc:
            consecutive_failures += 1
            failure = exc
            recovery_error = _record_failure(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=failure.code,
                message=failure.message,
                failed_at=datetime.now(timezone.utc),
                started_at=started_at,
                commit=True,
            )
            outcomes.append(
                AnalystRepositoryOutcome(
                    github_repository_id=repository.github_repository_id,
                    full_name=repository.full_name,
                    analysis_status=RepositoryAnalysisStatus.FAILED,
                    failure_code=failure.code,
                    failure_message=_join_messages(failure.message, recovery_error),
                    monetization_potential=None,
                    runtime_readme_artifact_path=readme_artifact_path,
                    runtime_analysis_artifact_path=analysis_artifact_path,
                )
            )
            if recovery_error is None:
                _emit_analysis_failure_event(
                    session,
                    agent_run_id=agent_run_id,
                    repository_id=repository.github_repository_id,
                    full_name=repository.full_name,
                    failure_code=failure.code,
                    message=_join_messages(failure.message, recovery_error) or failure.message,
                    classification=FailureClassification.BLOCKING,
                    failure_severity=determine_severity(
                        FailureClassification.BLOCKING,
                        consecutive_failures,
                    ),
                    consecutive_failures=consecutive_failures,
                    upstream_provider=None,
                )
                session.commit()
            _write_analyst_progress_snapshot(
                runtime_dir=runtime_dir,
                provider_name=provider_name,
                total_targets=total_targets,
                outcomes=outcomes,
                current_target=repository.full_name,
                current_activity="Recorded repository analysis failure.",
            )
        except GitHubRateLimitError as exc:
            consecutive_failures += 1
            failure_message = (
                f"{exc}. Analyst stopped early and left remaining repositories pending for retry."
            )
            recovery_error = _defer_retry(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=RepositoryAnalysisFailureCode.RATE_LIMITED,
                message=failure_message,
                deferred_at=datetime.now(timezone.utc),
                commit=True,
            )
            outcomes.append(
                AnalystRepositoryOutcome(
                    github_repository_id=repository.github_repository_id,
                    full_name=repository.full_name,
                    analysis_status=RepositoryAnalysisStatus.FAILED,
                    failure_code=RepositoryAnalysisFailureCode.RATE_LIMITED,
                    failure_message=_join_messages(failure_message, recovery_error),
                    monetization_potential=None,
                    runtime_readme_artifact_path=readme_artifact_path,
                    runtime_analysis_artifact_path=analysis_artifact_path,
                )
            )
            if recovery_error is None:
                classification = classify_github_error(exc)
                _emit_analysis_failure_event(
                    session,
                    agent_run_id=agent_run_id,
                    repository_id=repository.github_repository_id,
                    full_name=repository.full_name,
                    failure_code=RepositoryAnalysisFailureCode.RATE_LIMITED,
                    message=_join_messages(failure_message, recovery_error) or failure_message,
                    classification=classification,
                    failure_severity=determine_severity(classification, consecutive_failures),
                    consecutive_failures=consecutive_failures,
                    upstream_provider="github",
                    http_status_code=exc.status_code,
                    retry_after_seconds=exc.retry_after_seconds,
                )
                session.commit()
            _write_analyst_progress_snapshot(
                runtime_dir=runtime_dir,
                provider_name=provider_name,
                total_targets=total_targets,
                outcomes=outcomes,
                current_target=repository.full_name,
                current_activity="Waiting for GitHub rate limit window before retry.",
            )
            stopped_for_rate_limit = True
            break
        except GitHubPayloadError as exc:
            consecutive_failures += 1
            recovery_error = _record_failure(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=RepositoryAnalysisFailureCode.INVALID_README_PAYLOAD,
                message=str(exc),
                failed_at=datetime.now(timezone.utc),
                started_at=started_at,
                commit=True,
            )
            outcomes.append(
                AnalystRepositoryOutcome(
                    github_repository_id=repository.github_repository_id,
                    full_name=repository.full_name,
                    analysis_status=RepositoryAnalysisStatus.FAILED,
                    failure_code=RepositoryAnalysisFailureCode.INVALID_README_PAYLOAD,
                    failure_message=_join_messages(str(exc), recovery_error),
                    monetization_potential=None,
                    runtime_readme_artifact_path=readme_artifact_path,
                    runtime_analysis_artifact_path=analysis_artifact_path,
                )
            )
            if recovery_error is None:
                classification = classify_github_error(exc)
                _emit_analysis_failure_event(
                    session,
                    agent_run_id=agent_run_id,
                    repository_id=repository.github_repository_id,
                    full_name=repository.full_name,
                    failure_code=RepositoryAnalysisFailureCode.INVALID_README_PAYLOAD,
                    message=_join_messages(str(exc), recovery_error) or str(exc),
                    classification=classification,
                    failure_severity=determine_severity(classification, consecutive_failures),
                    consecutive_failures=consecutive_failures,
                    upstream_provider="github",
                )
                session.commit()
            _write_analyst_progress_snapshot(
                runtime_dir=runtime_dir,
                provider_name=provider_name,
                total_targets=total_targets,
                outcomes=outcomes,
                current_target=repository.full_name,
                current_activity="Captured invalid README payload failure.",
            )
        except ValidationError as exc:
            consecutive_failures += 1
            classification = FailureClassification.RETRYABLE
            recovery_error = _record_failure(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=RepositoryAnalysisFailureCode.INVALID_ANALYSIS_OUTPUT,
                message=str(exc),
                failed_at=datetime.now(timezone.utc),
                started_at=started_at,
                commit=True,
            )
            outcomes.append(
                AnalystRepositoryOutcome(
                    github_repository_id=repository.github_repository_id,
                    full_name=repository.full_name,
                    analysis_status=RepositoryAnalysisStatus.FAILED,
                    failure_code=RepositoryAnalysisFailureCode.INVALID_ANALYSIS_OUTPUT,
                    failure_message=_join_messages(str(exc), recovery_error),
                    monetization_potential=None,
                    runtime_readme_artifact_path=readme_artifact_path,
                    runtime_analysis_artifact_path=analysis_artifact_path,
                )
            )
            if recovery_error is None:
                _emit_analysis_failure_event(
                    session,
                    agent_run_id=agent_run_id,
                    repository_id=repository.github_repository_id,
                    full_name=repository.full_name,
                    failure_code=RepositoryAnalysisFailureCode.INVALID_ANALYSIS_OUTPUT,
                    message=_join_messages(str(exc), recovery_error) or str(exc),
                    classification=classification,
                    failure_severity=determine_severity(classification, consecutive_failures),
                    consecutive_failures=consecutive_failures,
                    upstream_provider="llm",
                )
                session.commit()
            _write_analyst_progress_snapshot(
                runtime_dir=runtime_dir,
                provider_name=provider_name,
                total_targets=total_targets,
                outcomes=outcomes,
                current_target=repository.full_name,
                current_activity="Captured invalid model output failure.",
            )
        except GitHubProviderError as exc:
            consecutive_failures += 1
            recovery_error = _record_failure(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=RepositoryAnalysisFailureCode.TRANSPORT_ERROR,
                message=str(exc),
                failed_at=datetime.now(timezone.utc),
                started_at=started_at,
                commit=True,
            )
            outcomes.append(
                AnalystRepositoryOutcome(
                    github_repository_id=repository.github_repository_id,
                    full_name=repository.full_name,
                    analysis_status=RepositoryAnalysisStatus.FAILED,
                    failure_code=RepositoryAnalysisFailureCode.TRANSPORT_ERROR,
                    failure_message=_join_messages(str(exc), recovery_error),
                    monetization_potential=None,
                    runtime_readme_artifact_path=readme_artifact_path,
                    runtime_analysis_artifact_path=analysis_artifact_path,
                )
            )
            if recovery_error is None:
                classification = classify_github_error(exc)
                _emit_analysis_failure_event(
                    session,
                    agent_run_id=agent_run_id,
                    repository_id=repository.github_repository_id,
                    full_name=repository.full_name,
                    failure_code=RepositoryAnalysisFailureCode.TRANSPORT_ERROR,
                    message=_join_messages(str(exc), recovery_error) or str(exc),
                    classification=classification,
                    failure_severity=determine_severity(classification, consecutive_failures),
                    consecutive_failures=consecutive_failures,
                    upstream_provider="github",
                )
                session.commit()
            _write_analyst_progress_snapshot(
                runtime_dir=runtime_dir,
                provider_name=provider_name,
                total_targets=total_targets,
                outcomes=outcomes,
                current_target=repository.full_name,
                current_activity="Captured GitHub transport failure.",
            )
        except Exception as exc:
            consecutive_failures += 1
            rollback_error = _rollback_after_failure(session)
            recovery_error = _record_failure(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=RepositoryAnalysisFailureCode.PERSISTENCE_ERROR,
                message=str(exc),
                failed_at=datetime.now(timezone.utc),
                started_at=started_at,
                commit=True,
            )
            outcomes.append(
                AnalystRepositoryOutcome(
                    github_repository_id=repository.github_repository_id,
                    full_name=repository.full_name,
                    analysis_status=RepositoryAnalysisStatus.FAILED,
                    failure_code=RepositoryAnalysisFailureCode.PERSISTENCE_ERROR,
                    failure_message=_join_messages(str(exc), rollback_error, recovery_error),
                    monetization_potential=None,
                    runtime_readme_artifact_path=readme_artifact_path,
                    runtime_analysis_artifact_path=analysis_artifact_path,
                )
            )
            if recovery_error is None:
                _emit_analysis_failure_event(
                    session,
                    agent_run_id=agent_run_id,
                    repository_id=repository.github_repository_id,
                    full_name=repository.full_name,
                    failure_code=RepositoryAnalysisFailureCode.PERSISTENCE_ERROR,
                    message=_join_messages(str(exc), rollback_error, recovery_error) or str(exc),
                    classification=FailureClassification.RETRYABLE,
                    failure_severity=determine_severity(
                        FailureClassification.RETRYABLE,
                        consecutive_failures,
                    ),
                    consecutive_failures=consecutive_failures,
                    upstream_provider=None,
                )
                session.commit()
            _write_analyst_progress_snapshot(
                runtime_dir=runtime_dir,
                provider_name=provider_name,
                total_targets=total_targets,
                outcomes=outcomes,
                current_target=repository.full_name,
                current_activity="Captured persistence failure.",
            )

    status = _determine_status(
        outcomes,
        interrupted=interrupted,
        paused=is_agent_paused(session, "analyst"),
    )
    artifact_path: Path | None = None
    artifact_error: str | None = None
    try:
        artifact_path = artifact_writer(
            runtime_dir=runtime_dir,
            status=status,
            outcomes=outcomes,
        )
    except OSError as exc:
        artifact_error = str(exc)
        if status is AnalystRunStatus.SUCCESS:
            status = AnalystRunStatus.PARTIAL_FAILURE

    _write_analyst_progress_snapshot(
        runtime_dir=runtime_dir,
        provider_name=provider_name,
        total_targets=total_targets,
        outcomes=outcomes,
        current_target=None,
        current_activity=(
            "Analyst stopped early because GitHub rate limiting is active."
            if stopped_for_rate_limit
            else (
                "Analyst run completed."
                if status is AnalystRunStatus.SUCCESS
                else "Analyst run finished with warnings or failures."
            )
        ),
        status_label=status.value.replace("_", " "),
    )

    return AnalystRunResult(
        status=status,
        outcomes=outcomes,
        artifact_path=artifact_path,
        artifact_error=artifact_error,
        provider_name=provider_name,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


@dataclass(frozen=True, slots=True)
class _AnalystFailure(Exception):
    code: RepositoryAnalysisFailureCode
    message: str


def _write_analyst_progress_snapshot(
    *,
    runtime_dir: Path | None,
    provider_name: str | None,
    total_targets: int,
    outcomes: list[AnalystRepositoryOutcome],
    current_target: str | None,
    current_activity: str,
    status_label: str = "running",
) -> None:
    completed_count = len(outcomes)
    failed_count = sum(
        1 for outcome in outcomes if outcome.analysis_status is RepositoryAnalysisStatus.FAILED
    )
    progress_percent = int(round((completed_count / total_targets) * 100)) if total_targets > 0 else None
    try:
        write_agent_progress_snapshot(
            runtime_dir=runtime_dir,
            agent_name="analyst",
            payload={
                "status_label": status_label,
                "current_activity": current_activity,
                "current_target": current_target,
                "completed_count": completed_count,
                "total_count": total_targets,
                "remaining_count": max(total_targets - completed_count, 0),
                "progress_percent": progress_percent,
                "unit_label": "repos",
                "source": "analyst queue snapshot",
                "details": [
                    f"Completed outcomes: {completed_count}",
                    f"Failed outcomes: {failed_count}",
                    f"Provider: {provider_name or 'unknown'}",
                ],
            },
        )
    except OSError:
        logger.warning("Failed to write analyst progress snapshot", exc_info=True)


def _rollback_after_failure(session: Session) -> str | None:
    try:
        session.rollback()
    except Exception as exc:
        return f"rollback failed: {exc}"
    return None


def _record_failure(
    *,
    session: Session,
    repository_id: int,
    failure_code: RepositoryAnalysisFailureCode,
    message: str,
    failed_at: datetime,
    started_at: datetime,
    commit: bool = True,
) -> str | None:
    rollback_error = _rollback_after_failure(session)
    try:
        persist_analysis_failure(
            session,
            repository_id=repository_id,
            failure_code=failure_code,
            message=message,
            failed_at=failed_at,
            started_at=started_at,
            commit=commit,
        )
    except Exception as exc:
        _rollback_after_failure(session)
        return _join_messages(rollback_error, f"failure status update skipped: {exc}")
    return rollback_error


def _defer_retry(
    *,
    session: Session,
    repository_id: int,
    failure_code: RepositoryAnalysisFailureCode,
    message: str,
    deferred_at: datetime,
    commit: bool = True,
) -> str | None:
    rollback_error = _rollback_after_failure(session)
    try:
        defer_analysis_retry(
            session,
            repository_id=repository_id,
            failure_code=failure_code,
            message=message,
            deferred_at=deferred_at,
            commit=commit,
        )
    except Exception as exc:
        _rollback_after_failure(session)
        return _join_messages(rollback_error, f"retry defer skipped: {exc}")
    return rollback_error


def _join_messages(*messages: str | None) -> str | None:
    parts = [message for message in messages if message]
    if not parts:
        return None
    return " | ".join(parts)


def _emit_analysis_failure_event(
    session: Session,
    *,
    agent_run_id: int | None,
    repository_id: int,
    full_name: str,
    failure_code: RepositoryAnalysisFailureCode,
    message: str,
    classification: FailureClassification,
    failure_severity: FailureSeverity,
    upstream_provider: str | None,
    consecutive_failures: int = 1,
    http_status_code: int | None = None,
    retry_after_seconds: int | None = None,
) -> None:
    try:
        effective_classification = classification
        effective_severity = failure_severity
        should_allow_pause = True

        # Missing README is an expected repository-level miss for Analyst. Even if a
        # README 404 reaches the generic failure-event path, treat it as non-pausing.
        if (
            failure_code is RepositoryAnalysisFailureCode.MISSING_README
            and upstream_provider == "github"
        ):
            effective_classification = FailureClassification.RETRYABLE
            effective_severity = FailureSeverity.WARNING
            should_allow_pause = False

        event_id = emit_failure_event(
            session,
            event_type="repository_analysis_failed",
            agent_name="analyst",
            message=message,
            classification=effective_classification,
            failure_severity=effective_severity,
            http_status_code=http_status_code,
            retry_after_seconds=retry_after_seconds,
            affected_repository_id=repository_id,
            upstream_provider=upstream_provider,
            context_json=json.dumps(
                {
                    "github_repository_id": repository_id,
                    "full_name": full_name,
                    "failure_code": failure_code.value,
                },
                sort_keys=True,
            ),
            agent_run_id=agent_run_id,
        )
        decision = evaluate_pause_policy(
            "analyst",
            effective_classification,
            effective_severity,
            consecutive_failures,
            upstream_provider,
        )
        if should_allow_pause and decision.should_pause:
            execute_pause(session, decision, event_id)
            pause_context = json.dumps({
                "pause_reason": decision.reason,
                "resume_condition": decision.resume_condition,
                "is_paused": True,
            })
            emit_failure_event(
                session,
                event_type="agent_paused",
                agent_name="analyst",
                message=f"analyst paused: {decision.reason}",
                classification=effective_classification,
                failure_severity="critical",
                upstream_provider=upstream_provider,
                context_json=pause_context,
                agent_run_id=agent_run_id,
            )
    except Exception:
        session.rollback()
        logger.warning(
            "Failed to emit repository_analysis_failed event for %s (run_id=%s)",
            full_name,
            agent_run_id,
            exc_info=True,
        )


def _analysis_failure_code_for_llm(
    classification: FailureClassification,
) -> RepositoryAnalysisFailureCode:
    if classification is FailureClassification.RATE_LIMITED:
        return RepositoryAnalysisFailureCode.RATE_LIMITED
    return RepositoryAnalysisFailureCode.TRANSPORT_ERROR


def _extract_http_status_code(error: Exception) -> int | None:
    for attribute_name in ("status_code", "status", "http_status"):
        value = getattr(error, attribute_name, None)
        if isinstance(value, int):
            return value
    return None


def _extract_retry_after_seconds(error: Exception) -> int | None:
    for attr in ("retry_after_seconds", "retry_after", "ratelimit_reset", "reset_timestamp"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            if attr == "reset_timestamp":
                import time
                return max(0, value - int(time.time()))
            return value
    return None


def _gather_repository_intelligence(
    *,
    provider: object,
    owner_login: str,
    repository_name: str,
) -> dict[str, object]:
    metadata_fn = getattr(provider, "get_repository_metadata", None)
    if not callable(metadata_fn):
        return {}

    intelligence: dict[str, object] = {}
    try:
        metadata = metadata_fn(owner_login=owner_login, repository_name=repository_name)
    except Exception:
        return {}

    intelligence["metadata"] = _to_jsonable(metadata)
    default_ref = getattr(metadata, "default_branch", None) or "HEAD"

    for key, fn_name, kwargs in (
        ("contributors", "list_contributors", {"limit": 5}),
        ("releases", "list_releases", {"limit": 10}),
        ("recent_commits", "list_recent_commits", {"limit": 100}),
        ("recent_pull_requests", "list_recent_pull_requests", {"limit": 50}),
        ("recent_issues", "list_recent_issues", {"limit": 50}),
    ):
        fn = getattr(provider, fn_name, None)
        if not callable(fn):
            continue
        try:
            payload = fn(owner_login=owner_login, repository_name=repository_name, **kwargs)
        except Exception:
            continue
        intelligence[key] = [_to_jsonable(item) for item in payload]

    tree_fn = getattr(provider, "get_repository_tree", None)
    tree_entries: list[object] = []
    if callable(tree_fn):
        try:
            tree_entries = tree_fn(
                owner_login=owner_login,
                repository_name=repository_name,
                ref=default_ref,
                depth_limit=2,
            )
        except Exception:
            tree_entries = []
    intelligence["tree_paths"] = [
        path
        for path in (_extract_tree_path(entry) for entry in tree_entries)
        if path is not None
    ]

    selected_files: dict[str, str] = {}
    file_contents_fn = getattr(provider, "get_file_contents", None)
    if callable(file_contents_fn):
        for path in _choose_selected_files(intelligence.get("tree_paths", [])):
            try:
                snapshot = file_contents_fn(
                    owner_login=owner_login,
                    repository_name=repository_name,
                    path=path,
                )
            except Exception:
                continue
            if snapshot is None:
                continue
            content = getattr(snapshot, "content", None)
            if isinstance(content, str) and content.strip():
                selected_files[path] = content[:4000]
    intelligence["selected_files"] = selected_files

    return intelligence


def _choose_selected_files(tree_paths: object) -> list[str]:
    if not isinstance(tree_paths, list):
        return []
    path_set = {path for path in tree_paths if isinstance(path, str)}
    selected: list[str] = []
    for candidate in _SELECTED_EVIDENCE_FILES:
        if candidate in path_set:
            selected.append(candidate)
    for path in sorted(path_set):
        if path.startswith(".github/workflows/") and len(selected) < 8:
            selected.append(path)
    return selected[:8]


def _extract_tree_path(entry: object) -> str | None:
    if is_dataclass(entry):
        payload = asdict(entry)
        value = payload.get("path")
        return value if isinstance(value, str) else None
    if isinstance(entry, dict):
        value = entry.get("path")
        return value if isinstance(value, str) else None
    return None


def _to_jsonable(value: object) -> object:
    if is_dataclass(value):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    return value


def _should_run_deep_analysis(
    *,
    repository: object,
    evidence: object,
    analysis: object,
) -> bool:
    stars = int(getattr(repository, "stargazers_count", 0) or 0)
    confidence = int(getattr(analysis, "confidence_score", 0) or 0)
    category_confidence = int(getattr(analysis, "category_confidence_score", 0) or 0)
    signals = getattr(evidence, "signals", {})
    if not isinstance(signals, dict):
        return False
    recent_commit_count = int(signals.get("recent_commit_count_90d", 0) or 0)
    contributors_count = int(signals.get("contributors_count", 0) or 0)
    has_dual_surface = bool(signals.get("has_frontend_surface")) and bool(
        signals.get("has_backend_surface")
    )
    score_breakdown = getattr(evidence, "score_breakdown", {})
    if not isinstance(score_breakdown, dict):
        score_breakdown = {}
    hosted_gap_score = int(score_breakdown.get("hosted_gap_score", 0) or 0)
    market_timing_score = int(score_breakdown.get("market_timing_score", 0) or 0)
    return (
        stars >= 200
        or recent_commit_count >= 20
        or hosted_gap_score >= 65
        or market_timing_score >= 70
        or (
            has_dual_surface
            and contributors_count >= 2
            and confidence >= 60
            and category_confidence >= 50
        )
    )


def _determine_status(
    outcomes: list[AnalystRepositoryOutcome],
    *,
    interrupted: bool = False,
    paused: bool = False,
) -> AnalystRunStatus:
    has_error = any(outcome.failure_code is not None or outcome.artifact_error for outcome in outcomes)
    if interrupted and paused and not has_error:
        return AnalystRunStatus.SKIPPED_PAUSED
    if interrupted and not has_error:
        return AnalystRunStatus.SKIPPED
    has_success = any(outcome.failure_code is None for outcome in outcomes)
    if has_error and has_success:
        return AnalystRunStatus.PARTIAL_FAILURE
    if has_error:
        return AnalystRunStatus.FAILED
    return AnalystRunStatus.SUCCESS


def _write_run_artifact(
    *,
    runtime_dir: Path | None,
    status: AnalystRunStatus,
    outcomes: list[AnalystRepositoryOutcome],
) -> Path | None:
    if runtime_dir is None:
        return None

    artifact_dir = runtime_dir / "analyst" / "analysis-runs"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    artifact_path = artifact_dir / f"{timestamp}.json"
    artifact_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": status.value,
                "summary": {
                    "completed": sum(
                        outcome.analysis_status is RepositoryAnalysisStatus.COMPLETED
                        for outcome in outcomes
                    ),
                    "failed": sum(
                        outcome.analysis_status is RepositoryAnalysisStatus.FAILED
                        for outcome in outcomes
                    ),
                },
                "outcomes": [
                    {
                        "github_repository_id": outcome.github_repository_id,
                        "full_name": outcome.full_name,
                        "analysis_status": outcome.analysis_status.value,
                        "failure_code": (
                            outcome.failure_code.value if outcome.failure_code is not None else None
                        ),
                        "failure_message": outcome.failure_message,
                        "monetization_potential": outcome.monetization_potential,
                        "runtime_readme_artifact_path": outcome.runtime_readme_artifact_path,
                        "runtime_analysis_artifact_path": outcome.runtime_analysis_artifact_path,
                        "artifact_error": outcome.artifact_error,
                    }
                    for outcome in outcomes
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return artifact_path

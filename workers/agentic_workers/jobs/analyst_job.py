from __future__ import annotations

from dataclasses import dataclass
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
from agentic_workers.providers.readme_analyst import (
    HeuristicReadmeAnalysisProvider,
    ReadmeAnalysisProvider,
    ReadmeBusinessAnalysis,
    normalize_readme,
)
from agentic_workers.storage.analysis_store import (
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
        logger.info("Analyst is paused, skipping run")
        return AnalystRunResult(
            status=AnalystRunStatus.SKIPPED_PAUSED,
            outcomes=[],
            artifact_path=None,
        )

    effective_analysis_provider = analysis_provider or HeuristicReadmeAnalysisProvider()
    artifact_writer = write_artifact or _write_run_artifact

    outcomes: list[AnalystRepositoryOutcome] = []
    interrupted = False
    consecutive_failures = 0
    for repository in list_pending_analysis_targets(session):
        if should_stop is not None and should_stop():
            interrupted = True
            break

        started_at = datetime.now(timezone.utc)
        readme_artifact_path: str | None = None
        analysis_artifact_path: str | None = None
        try:
            mark_analysis_in_progress(session, repository=repository, started_at=started_at)

            readme = provider.get_readme(
                owner_login=repository.owner_login,
                repository_name=repository.repository_name,
            )
            normalized = normalize_readme(readme.content)
            if not normalized.normalized_text:
                raise _AnalystFailure(
                    code=RepositoryAnalysisFailureCode.MISSING_README,
                    message="README content was empty after normalization.",
                )

            try:
                raw_analysis = effective_analysis_provider.analyze(
                    repository_full_name=repository.full_name,
                    readme=normalized,
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
            analysis = ReadmeBusinessAnalysis.model_validate_json(raw_analysis)
            completed_at = datetime.now(timezone.utc)

            persisted = persist_analysis_success(
                session,
                repository_id=repository.github_repository_id,
                repository_full_name=repository.full_name,
                runtime_dir=runtime_dir,
                normalized_readme=normalized.normalized_text,
                readme_source_url=readme.source_url,
                readme_fetched_at=readme.fetched_at,
                normalization_version="story-3.4-v1",
                raw_character_count=normalized.raw_character_count,
                normalized_character_count=normalized.normalized_character_count,
                removed_line_count=normalized.removed_line_count,
                analysis=analysis,
                analysis_provider_name=effective_analysis_provider.__class__.__name__,
                completed_at=completed_at,
            )
            readme_artifact_path = persisted.readme_artifact.runtime_relative_path
            analysis_artifact_path = persisted.analysis_artifact.runtime_relative_path
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
        except GitHubReadmeNotFoundError as exc:
            # Missing READMEs are common in the wild and should not behave like
            # operator-blocking system outages. Record the repo failure, but do
            # not escalate it into an analyst pause cascade.
            consecutive_failures = 0
            recovery_error = _record_failure(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=RepositoryAnalysisFailureCode.MISSING_README,
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
                    failure_code=RepositoryAnalysisFailureCode.MISSING_README,
                    failure_message=_join_messages(str(exc), recovery_error),
                    monetization_potential=None,
                    runtime_readme_artifact_path=readme_artifact_path,
                    runtime_analysis_artifact_path=analysis_artifact_path,
                )
            )
            if recovery_error is None:
                emit_failure_event(
                    session,
                    event_type="repository_analysis_failed",
                    agent_name="analyst",
                    message=_join_messages(str(exc), recovery_error) or str(exc),
                    classification=FailureClassification.RETRYABLE,
                    failure_severity=FailureSeverity.WARNING,
                    affected_repository_id=repository.github_repository_id,
                    upstream_provider="github",
                    context_json=json.dumps(
                        {
                            "github_repository_id": repository.github_repository_id,
                            "full_name": repository.full_name,
                            "failure_code": RepositoryAnalysisFailureCode.MISSING_README.value,
                            "handling": "missing_readme_non_blocking",
                        },
                        sort_keys=True,
                    ),
                    agent_run_id=agent_run_id,
                )
                session.commit()
        except GitHubRateLimitError as exc:
            consecutive_failures += 1
            recovery_error = _record_failure(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=RepositoryAnalysisFailureCode.RATE_LIMITED,
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
                    failure_code=RepositoryAnalysisFailureCode.RATE_LIMITED,
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
                    failure_code=RepositoryAnalysisFailureCode.RATE_LIMITED,
                    message=_join_messages(str(exc), recovery_error) or str(exc),
                    classification=classification,
                    failure_severity=determine_severity(classification, consecutive_failures),
                    consecutive_failures=consecutive_failures,
                    upstream_provider="github",
                    http_status_code=exc.status_code,
                    retry_after_seconds=exc.retry_after_seconds,
                )
                session.commit()
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
        except ValidationError as exc:
            consecutive_failures += 1
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
                    classification=FailureClassification.BLOCKING,
                    failure_severity=determine_severity(
                        FailureClassification.BLOCKING,
                        consecutive_failures,
                    ),
                    consecutive_failures=consecutive_failures,
                    upstream_provider="llm",
                )
                session.commit()
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

    status = _determine_status(
        outcomes,
        interrupted=interrupted,
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

    return AnalystRunResult(
        status=status,
        outcomes=outcomes,
        artifact_path=artifact_path,
        artifact_error=artifact_error,
    )


@dataclass(frozen=True, slots=True)
class _AnalystFailure(Exception):
    code: RepositoryAnalysisFailureCode
    message: str


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
        event_id = emit_failure_event(
            session,
            event_type="repository_analysis_failed",
            agent_name="analyst",
            message=message,
            classification=classification,
            failure_severity=failure_severity,
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
        decision = evaluate_pause_policy("analyst", classification, failure_severity, consecutive_failures, upstream_provider)
        if decision.should_pause:
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
                classification=classification,
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


def _determine_status(
    outcomes: list[AnalystRepositoryOutcome],
    *,
    interrupted: bool = False,
) -> AnalystRunStatus:
    has_error = any(outcome.failure_code is not None or outcome.artifact_error for outcome in outcomes)
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

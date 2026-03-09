from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
from typing import Callable

from pydantic import ValidationError
from sqlmodel import Session

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
    RepositoryAnalysisFailureCode,
    RepositoryAnalysisStatus,
)


class AnalystRunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


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
) -> AnalystRunResult:
    effective_analysis_provider = analysis_provider or HeuristicReadmeAnalysisProvider()
    artifact_writer = write_artifact or _write_run_artifact

    outcomes: list[AnalystRepositoryOutcome] = []
    for repository in list_pending_analysis_targets(session):
        if should_stop is not None and should_stop():
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

            raw_analysis = effective_analysis_provider.analyze(
                repository_full_name=repository.full_name,
                readme=normalized,
            )
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
            failure = exc
            recovery_error = _record_failure(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=failure.code,
                message=failure.message,
                failed_at=datetime.now(timezone.utc),
                started_at=started_at,
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
        except GitHubReadmeNotFoundError as exc:
            recovery_error = _record_failure(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=RepositoryAnalysisFailureCode.MISSING_README,
                message=str(exc),
                failed_at=datetime.now(timezone.utc),
                started_at=started_at,
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
        except GitHubRateLimitError as exc:
            recovery_error = _record_failure(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=RepositoryAnalysisFailureCode.RATE_LIMITED,
                message=str(exc),
                failed_at=datetime.now(timezone.utc),
                started_at=started_at,
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
        except GitHubPayloadError as exc:
            recovery_error = _record_failure(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=RepositoryAnalysisFailureCode.INVALID_README_PAYLOAD,
                message=str(exc),
                failed_at=datetime.now(timezone.utc),
                started_at=started_at,
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
        except ValidationError as exc:
            recovery_error = _record_failure(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=RepositoryAnalysisFailureCode.INVALID_ANALYSIS_OUTPUT,
                message=str(exc),
                failed_at=datetime.now(timezone.utc),
                started_at=started_at,
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
        except GitHubProviderError as exc:
            recovery_error = _record_failure(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=RepositoryAnalysisFailureCode.TRANSPORT_ERROR,
                message=str(exc),
                failed_at=datetime.now(timezone.utc),
                started_at=started_at,
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
        except Exception as exc:
            rollback_error = _rollback_after_failure(session)
            recovery_error = _record_failure(
                session=session,
                repository_id=repository.github_repository_id,
                failure_code=RepositoryAnalysisFailureCode.PERSISTENCE_ERROR,
                message=str(exc),
                failed_at=datetime.now(timezone.utc),
                started_at=started_at,
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

    status = _determine_status(outcomes)
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


def _determine_status(outcomes: list[AnalystRepositoryOutcome]) -> AnalystRunStatus:
    has_error = any(outcome.failure_code is not None or outcome.artifact_error for outcome in outcomes)
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

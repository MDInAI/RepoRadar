from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
from typing import Callable, Protocol

from sqlmodel import Session

from agentic_workers.providers.github_provider import DiscoveredRepository, FirehoseMode
from agentic_workers.storage.repository_intake import (
    IntakePersistenceResult,
    persist_firehose_batch,
)


class FirehoseRunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class FirehoseModeOutcome:
    mode: FirehoseMode
    fetched_count: int
    inserted_count: int
    skipped_count: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class FirehoseRunResult:
    status: FirehoseRunStatus
    outcomes: list[FirehoseModeOutcome]
    artifact_path: Path | None
    artifact_error: str | None = None


class FirehoseProvider(Protocol):
    def discover(
        self,
        *,
        mode: FirehoseMode,
        per_page: int = 25,
        page: int = 1,
    ) -> list[DiscoveredRepository]: ...


PersistBatchFn = Callable[
    [Session, list[DiscoveredRepository]],
    IntakePersistenceResult,
]
ArtifactWriter = Callable[..., Path | None]


def run_firehose_job(
    *,
    session: Session,
    provider: FirehoseProvider,
    runtime_dir: Path | None,
    pacing_seconds: int,
    modes: tuple[FirehoseMode, ...] = (FirehoseMode.NEW, FirehoseMode.TRENDING),
    per_page: int = 100,
    page: int = 1,
    pages: int = 1,
    sleep_fn: Callable[[int], None],
    should_stop: Callable[[], bool] | None = None,
    persist_batch: Callable[
        [Session, list[DiscoveredRepository]],
        IntakePersistenceResult,
    ]
    | None = None,
    write_artifact: ArtifactWriter | None = None,
) -> FirehoseRunResult:
    persistence = persist_batch or _persist_batch
    artifact_writer = write_artifact or _write_run_artifact
    outcomes: list[FirehoseModeOutcome] = []

    for index, mode in enumerate(modes):
        # Honour a shutdown signal before starting each new discovery mode.
        if should_stop is not None and should_stop():
            break

        repositories: list[DiscoveredRepository] = []
        try:
            for page_num in range(page, page + pages):
                if should_stop is not None and should_stop():
                    break
                page_repos = provider.discover(mode=mode, per_page=per_page, page=page_num)
                repositories.extend(page_repos)
                if len(page_repos) < per_page:
                    # Partial page means no further results exist for this mode.
                    break
            persisted = persistence(session, repositories, mode=mode)
            outcomes.append(
                FirehoseModeOutcome(
                    mode=mode,
                    fetched_count=len(repositories),
                    inserted_count=persisted.inserted_count,
                    skipped_count=persisted.skipped_count,
                )
            )
        except Exception as exc:
            rollback = getattr(session, "rollback", None)
            if callable(rollback):
                rollback()
            outcomes.append(
                FirehoseModeOutcome(
                    mode=mode,
                    fetched_count=len(repositories),
                    inserted_count=0,
                    skipped_count=0,
                    error=str(exc),
                )
            )

        if index < len(modes) - 1:
            sleep_fn(pacing_seconds)

    status = _determine_status(outcomes)
    artifact_path: Path | None = None
    artifact_error: str | None = None
    try:
        artifact_path = artifact_writer(runtime_dir=runtime_dir, status=status, outcomes=outcomes)
    except OSError as exc:
        artifact_error = str(exc)
        if status is FirehoseRunStatus.SUCCESS:
            status = FirehoseRunStatus.PARTIAL_FAILURE
    return FirehoseRunResult(
        status=status,
        outcomes=outcomes,
        artifact_path=artifact_path,
        artifact_error=artifact_error,
    )


def _persist_batch(
    session: Session,
    repositories: list[DiscoveredRepository],
    *,
    mode: FirehoseMode,
) -> IntakePersistenceResult:
    return persist_firehose_batch(session, repositories, mode=mode)


def _determine_status(outcomes: list[FirehoseModeOutcome]) -> FirehoseRunStatus:
    has_error = any(outcome.error for outcome in outcomes)
    # Any outcome that completed without an error counts as a success, even when it
    # returned an empty batch — zero results is valid data, not a failure.
    has_success = any(outcome.error is None for outcome in outcomes)
    if has_error and has_success:
        return FirehoseRunStatus.PARTIAL_FAILURE
    if has_error:
        return FirehoseRunStatus.FAILED
    return FirehoseRunStatus.SUCCESS


def _write_run_artifact(
    *,
    runtime_dir: Path | None,
    status: FirehoseRunStatus,
    outcomes: list[FirehoseModeOutcome],
) -> Path | None:
    if runtime_dir is None:
        return None

    artifact_dir = runtime_dir / "firehose" / "ingestion-runs"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_path = artifact_dir / f"{timestamp}.json"
    artifact_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": status.value,
                "outcomes": [
                    {
                        **asdict(outcome),
                        "mode": outcome.mode.value,
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

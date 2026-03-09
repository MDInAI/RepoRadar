from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
import json
from pathlib import Path
from typing import Callable, Protocol

from sqlmodel import Session

from agentic_workers.providers.github_provider import (
    DiscoveredRepository,
    GitHubRateLimitError,
)
from agentic_workers.storage.backfill_progress import (
    BackfillCheckpointState,
    advance_backfill_progress,
    initialize_backfill_progress,
    load_backfill_progress,
    save_backfill_progress,
)
from agentic_workers.storage.intake_progress_snapshots import (
    write_backfill_progress_snapshot,
)
from agentic_workers.storage.repository_intake import (
    IntakePersistenceResult,
    persist_backfill_batch,
)


class BackfillRunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class BackfillPageOutcome:
    window_start_date: date
    created_before_boundary: date
    created_before_cursor: datetime | None
    page: int
    fetched_count: int
    inserted_count: int
    skipped_count: int
    exhausted_after: bool
    error: str | None = None
    rate_limit_backoff_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class BackfillRunResult:
    status: BackfillRunStatus
    outcomes: list[BackfillPageOutcome]
    checkpoint: BackfillCheckpointState
    artifact_path: Path | None
    artifact_error: str | None = None


class BackfillProvider(Protocol):
    def discover_backfill(
        self,
        *,
        window_start_date: date,
        created_before_boundary: date,
        created_before_cursor: datetime | None = None,
        per_page: int = 25,
        page: int = 1,
    ) -> list[DiscoveredRepository]: ...


PersistBackfillBatchFn = Callable[[Session, list[DiscoveredRepository]], IntakePersistenceResult]
LoadCheckpointFn = Callable[[Session], BackfillCheckpointState | None]
SaveCheckpointFn = Callable[[Session, BackfillCheckpointState], None]
ArtifactWriter = Callable[..., Path | None]


def run_backfill_job(
    *,
    session: Session,
    provider: BackfillProvider,
    runtime_dir: Path | None,
    pacing_seconds: int,
    per_page: int,
    pages: int,
    window_days: int,
    min_created_date: date,
    sleep_fn: Callable[[int], None],
    should_stop: Callable[[], bool] | None = None,
    persist_batch: PersistBackfillBatchFn | None = None,
    load_progress: LoadCheckpointFn | None = None,
    save_progress: SaveCheckpointFn | None = None,
    write_artifact: ArtifactWriter | None = None,
    today: date | None = None,
) -> BackfillRunResult:
    if window_days <= 0:
        raise ValueError("window_days must be greater than zero")

    checkpoint_loader = load_progress or _load_checkpoint
    checkpoint_saver = save_progress or _save_checkpoint
    persistence = persist_batch or _persist_batch
    artifact_writer = write_artifact or _write_run_artifact
    active_today = today or _utc_today()
    checkpoint = checkpoint_loader(session) or initialize_backfill_progress(
        today=active_today,
        window_days=window_days,
        min_created_date=min_created_date,
    )
    outcomes: list[BackfillPageOutcome] = []
    snapshot_errors: list[str] = []
    remaining_pages = max(0, pages - checkpoint.pages_processed_in_run)

    for page_index in range(remaining_pages):
        if checkpoint.exhausted:
            break
        if should_stop is not None and should_stop():
            break
        if page_index > 0:
            sleep_fn(pacing_seconds)
            if should_stop is not None and should_stop():
                break

        repositories: list[DiscoveredRepository] = []
        requested_page = checkpoint.next_page
        try:
            repositories = provider.discover_backfill(
                window_start_date=checkpoint.window_start_date,
                created_before_boundary=checkpoint.created_before_boundary,
                created_before_cursor=checkpoint.created_before_cursor,
                per_page=per_page,
                page=requested_page,
            )
            persisted = persistence(session, repositories)
            oldest_created_at = min(
                (repository.created_at for repository in repositories),
                default=None,
            )
            next_checkpoint = advance_backfill_progress(
                checkpoint,
                repositories_fetched=len(repositories),
                oldest_created_at=oldest_created_at,
                batch_has_mixed_timestamps=(
                    oldest_created_at is not None
                    and any(
                        repository.created_at > oldest_created_at
                        for repository in repositories
                    )
                ),
                per_page=per_page,
                window_days=window_days,
                min_created_date=min_created_date,
                checkpointed_at=datetime.now(timezone.utc),
                pages_processed_in_run=checkpoint.pages_processed_in_run + 1,
            )
            checkpoint_saver(session, next_checkpoint)
            session.commit()
            outcomes.append(
                BackfillPageOutcome(
                    window_start_date=checkpoint.window_start_date,
                    created_before_boundary=checkpoint.created_before_boundary,
                    created_before_cursor=checkpoint.created_before_cursor,
                    page=requested_page,
                    fetched_count=len(repositories),
                    inserted_count=persisted.inserted_count,
                    skipped_count=persisted.skipped_count,
                    exhausted_after=next_checkpoint.exhausted,
                )
            )
            checkpoint = next_checkpoint
        except GitHubRateLimitError as exc:
            session.rollback()
            backoff_seconds = max(
                pacing_seconds * 2,
                exc.retry_after_seconds or 0,
            )
            if backoff_seconds > 0 and (should_stop is None or not should_stop()):
                sleep_fn(backoff_seconds)
            outcomes.append(
                BackfillPageOutcome(
                    window_start_date=checkpoint.window_start_date,
                    created_before_boundary=checkpoint.created_before_boundary,
                    created_before_cursor=checkpoint.created_before_cursor,
                    page=requested_page,
                    fetched_count=len(repositories),
                    inserted_count=0,
                    skipped_count=0,
                    exhausted_after=checkpoint.exhausted,
                    error=str(exc),
                    rate_limit_backoff_seconds=backoff_seconds,
                )
            )
            break
        except Exception as exc:
            session.rollback()
            outcomes.append(
                BackfillPageOutcome(
                    window_start_date=checkpoint.window_start_date,
                    created_before_boundary=checkpoint.created_before_boundary,
                    created_before_cursor=checkpoint.created_before_cursor,
                    page=requested_page,
                    fetched_count=len(repositories),
                    inserted_count=0,
                    skipped_count=0,
                    exhausted_after=checkpoint.exhausted,
                    error=str(exc),
                )
            )
            break

    # Clear resume_required when the cycle completes without error or interruption,
    # so the next invocation gets a fresh page budget instead of a reduced one.
    cycle_had_errors = any(outcome.error for outcome in outcomes)
    cycle_was_interrupted = should_stop is not None and should_stop()
    
    # Write snapshot after the loop has completed. It'll represent either the last page successfully
    # processed or an error state if the loop aborted early.
    try:
        write_backfill_progress_snapshot(
            runtime_dir=runtime_dir,
            checkpoint=checkpoint,
        )
    except OSError as exc:
        snapshot_errors.append(f"snapshot write failed: {exc}")

    if checkpoint.resume_required and not cycle_had_errors and not cycle_was_interrupted:
        checkpoint = BackfillCheckpointState(
            source_provider=checkpoint.source_provider,
            window_start_date=checkpoint.window_start_date,
            created_before_boundary=checkpoint.created_before_boundary,
            created_before_cursor=checkpoint.created_before_cursor,
            next_page=checkpoint.next_page,
            exhausted=checkpoint.exhausted,
            last_checkpointed_at=checkpoint.last_checkpointed_at,
            resume_required=False,
            pages_processed_in_run=0,
        )
        checkpoint_saver(session, checkpoint)
        session.commit()

        # Update snapshot again to reflect the clear of resume_required
        try:
            write_backfill_progress_snapshot(
                runtime_dir=runtime_dir,
                checkpoint=checkpoint,
            )
        except OSError as exc:
            snapshot_errors.append(f"snapshot write failed: {exc}")

    status = _determine_status(outcomes)
    artifact_path: Path | None = None
    artifact_errors: list[str] = list(snapshot_errors)
    try:
        artifact_path = artifact_writer(
            runtime_dir=runtime_dir,
            status=status,
            outcomes=outcomes,
            checkpoint=checkpoint,
        )
    except OSError as exc:
        artifact_errors.append(str(exc))
        if status is BackfillRunStatus.SUCCESS:
            status = BackfillRunStatus.PARTIAL_FAILURE

    return BackfillRunResult(
        status=status,
        outcomes=outcomes,
        checkpoint=checkpoint,
        artifact_path=artifact_path,
        artifact_error="; ".join(artifact_errors) or None,
    )


def _persist_batch(
    session: Session,
    repositories: list[DiscoveredRepository],
) -> IntakePersistenceResult:
    return persist_backfill_batch(session, repositories, commit=False)


def _load_checkpoint(session: Session) -> BackfillCheckpointState | None:
    return load_backfill_progress(session)


def _save_checkpoint(session: Session, checkpoint: BackfillCheckpointState) -> None:
    save_backfill_progress(session, checkpoint, commit=False)


def _determine_status(outcomes: list[BackfillPageOutcome]) -> BackfillRunStatus:
    has_error = any(outcome.error for outcome in outcomes)
    has_success = any(outcome.error is None for outcome in outcomes)
    if has_error and has_success:
        return BackfillRunStatus.PARTIAL_FAILURE
    if has_error:
        return BackfillRunStatus.FAILED
    return BackfillRunStatus.SUCCESS


def _write_run_artifact(
    *,
    runtime_dir: Path | None,
    status: BackfillRunStatus,
    outcomes: list[BackfillPageOutcome],
    checkpoint: BackfillCheckpointState,
) -> Path | None:
    if runtime_dir is None:
        return None

    artifact_dir = runtime_dir / "backfill" / "ingestion-runs"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    artifact_path = artifact_dir / f"{timestamp}.json"
    artifact_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": status.value,
                "checkpoint": _serialize_checkpoint(checkpoint),
                "operator_guidance": {
                    "checkpoint_interpretation": (
                        "A non-null created_before_cursor means Backfill is paging through a dense "
                        "timestamp slice inside the current date window."
                    ),
                    "stall_recovery": (
                        "If dense results exceed GitHub's accessible search window, Backfill shrinks "
                        "created_before_cursor by one second and restarts at page 1."
                    ),
                    "rate_limit_handling": (
                        "If an outcome includes rate_limit_backoff_seconds, the worker paused for that "
                        "many seconds after a GitHub rate-limit response before ending the run."
                    ),
                },
                "outcomes": [
                    {
                        "window_start_date": outcome.window_start_date.isoformat(),
                        "window_end_date": (
                            outcome.created_before_boundary - timedelta(days=1)
                        ).isoformat(),
                        "created_before_boundary": outcome.created_before_boundary.isoformat(),
                        "created_before_cursor": (
                            outcome.created_before_cursor.isoformat()
                            if outcome.created_before_cursor is not None
                            else None
                        ),
                        "page": outcome.page,
                        "fetched_count": outcome.fetched_count,
                        "inserted_count": outcome.inserted_count,
                        "skipped_count": outcome.skipped_count,
                        "exhausted_after": outcome.exhausted_after,
                        "error": outcome.error,
                        "rate_limit_backoff_seconds": outcome.rate_limit_backoff_seconds,
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


def _serialize_checkpoint(checkpoint: BackfillCheckpointState) -> dict[str, str | int | bool | None]:
    return {
        "source_provider": checkpoint.source_provider,
        "window_start_date": checkpoint.window_start_date.isoformat(),
        "window_end_date": (checkpoint.created_before_boundary - timedelta(days=1)).isoformat(),
        "created_before_boundary": checkpoint.created_before_boundary.isoformat(),
        "created_before_cursor": (
            checkpoint.created_before_cursor.isoformat()
            if checkpoint.created_before_cursor is not None
            else None
        ),
        "next_page": checkpoint.next_page,
        "pages_processed_in_run": checkpoint.pages_processed_in_run,
        "exhausted": checkpoint.exhausted,
        "resume_required": checkpoint.resume_required,
        "last_checkpointed_at": (
            checkpoint.last_checkpointed_at.isoformat()
            if checkpoint.last_checkpointed_at is not None
            else None
        ),
    }


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()

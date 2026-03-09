from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
from typing import Callable, Protocol

from sqlmodel import Session

from agentic_workers.providers.github_provider import (
    DiscoveredRepository,
    FirehoseMode,
    GitHubRateLimitError,
)
from agentic_workers.storage.firehose_progress import (
    FirehoseCheckpointState,
    advance_firehose_progress,
    anchor_for_mode,
    clear_firehose_progress,
    initialize_firehose_progress,
    load_firehose_progress,
    save_firehose_progress,
)
from agentic_workers.storage.intake_progress_snapshots import (
    write_firehose_progress_snapshot,
)
from agentic_workers.storage.repository_intake import (
    IntakePersistenceResult,
    persist_firehose_batch,
)


class FirehoseRunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class FirehosePageOutcome:
    mode: FirehoseMode
    page: int
    anchor_date: date
    fetched_count: int
    inserted_count: int
    skipped_count: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class FirehoseRunResult:
    status: FirehoseRunStatus
    outcomes: list[FirehosePageOutcome]
    artifact_path: Path | None
    artifact_error: str | None = None


class FirehoseProvider(Protocol):
    def discover(
        self,
        *,
        mode: FirehoseMode,
        anchor_date: date | None = None,
        per_page: int = 25,
        page: int = 1,
    ) -> list[DiscoveredRepository]: ...


PersistBatchFn = Callable[
    [Session, list[DiscoveredRepository]],
    IntakePersistenceResult,
]
LoadCheckpointFn = Callable[[Session], FirehoseCheckpointState | None]
SaveCheckpointFn = Callable[[Session, FirehoseCheckpointState], None]
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
    load_progress: LoadCheckpointFn | None = None,
    save_progress: SaveCheckpointFn | None = None,
    write_artifact: ArtifactWriter | None = None,
    today: date | None = None,
) -> FirehoseRunResult:
    if not modes:
        raise ValueError("At least one Firehose mode must be configured")

    persistence = persist_batch or _persist_batch
    checkpoint_loader = load_progress or _load_checkpoint
    checkpoint_saver = save_progress or _save_checkpoint
    artifact_writer = write_artifact or _write_run_artifact
    active_today = today or _utc_today()
    checkpoint = checkpoint_loader(session)
    if checkpoint is None or not checkpoint.resume_required or checkpoint.active_mode is None:
        checkpoint = initialize_firehose_progress(today=active_today, active_mode=modes[0])

    outcomes: list[FirehosePageOutcome] = []
    sleep_between_requests = False
    snapshot_errors: list[str] = []

    while checkpoint.resume_required and checkpoint.active_mode is not None:
        mode = checkpoint.active_mode
        if checkpoint.pages_processed_in_run >= pages:
            checkpoint = _checkpoint_after_mode_page_budget(
                checkpoint=checkpoint,
                modes=modes,
                mode=mode,
                processed_pages=checkpoint.pages_processed_in_run,
                pages=pages,
            )
            checkpoint_saver(session, checkpoint)
            session.commit()
            try:
                write_firehose_progress_snapshot(
                    runtime_dir=runtime_dir,
                    checkpoint=checkpoint,
                )
            except OSError as exc:
                snapshot_errors.append(f"snapshot write failed: {exc}")
            continue
        if should_stop is not None and should_stop():
            break
        if sleep_between_requests:
            sleep_fn(pacing_seconds)
            if should_stop is not None and should_stop():
                break

        repositories: list[DiscoveredRepository] = []
        requested_page = checkpoint.next_page
        anchored_date = anchor_for_mode(checkpoint, mode)
        try:
            repositories = provider.discover(
                mode=mode,
                anchor_date=anchored_date,
                per_page=per_page,
                page=requested_page,
            )
            persisted = persistence(session, repositories, mode=mode)
            processed_pages = checkpoint.pages_processed_in_run + 1
            next_checkpoint = _next_checkpoint(
                checkpoint=checkpoint,
                modes=modes,
                fetched_count=len(repositories),
                per_page=per_page,
                checkpointed_at=datetime.now(timezone.utc),
                processed_pages=processed_pages,
            )
            next_checkpoint = _checkpoint_after_mode_page_budget(
                checkpoint=next_checkpoint,
                modes=modes,
                mode=mode,
                processed_pages=processed_pages,
                pages=pages,
            )
            checkpoint_saver(session, next_checkpoint)
            session.commit()
            try:
                write_firehose_progress_snapshot(
                    runtime_dir=runtime_dir,
                    checkpoint=next_checkpoint,
                )
            except OSError as exc:
                snapshot_errors.append(f"snapshot write failed: {exc}")
            outcomes.append(
                FirehosePageOutcome(
                    mode=mode,
                    page=requested_page,
                    anchor_date=anchored_date,
                    fetched_count=len(repositories),
                    inserted_count=persisted.inserted_count,
                    skipped_count=persisted.skipped_count,
                )
            )
            checkpoint = next_checkpoint
            sleep_between_requests = checkpoint.resume_required
        except GitHubRateLimitError as exc:
            session.rollback()
            backoff_seconds = max(
                pacing_seconds * 2,
                exc.retry_after_seconds or 0,
            )
            if backoff_seconds > 0 and (should_stop is None or not should_stop()):
                sleep_fn(backoff_seconds)
            outcomes.append(
                FirehosePageOutcome(
                    mode=mode,
                    page=requested_page,
                    anchor_date=anchored_date,
                    fetched_count=len(repositories),
                    inserted_count=0,
                    skipped_count=0,
                    error=str(exc),
                )
            )
            break
        except Exception as exc:
            session.rollback()
            outcomes.append(
                FirehosePageOutcome(
                    mode=mode,
                    page=requested_page,
                    anchor_date=anchored_date,
                    fetched_count=len(repositories),
                    inserted_count=0,
                    skipped_count=0,
                    error=str(exc),
                )
            )
            break

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
        if status is FirehoseRunStatus.SUCCESS:
            status = FirehoseRunStatus.PARTIAL_FAILURE
    return FirehoseRunResult(
        status=status,
        outcomes=outcomes,
        artifact_path=artifact_path,
        artifact_error="; ".join(artifact_errors) or None,
    )


def _persist_batch(
    session: Session,
    repositories: list[DiscoveredRepository],
    *,
    mode: FirehoseMode,
) -> IntakePersistenceResult:
    return persist_firehose_batch(session, repositories, mode=mode, commit=False)


def _load_checkpoint(session: Session) -> FirehoseCheckpointState | None:
    return load_firehose_progress(session)


def _save_checkpoint(session: Session, checkpoint: FirehoseCheckpointState) -> None:
    save_firehose_progress(session, checkpoint, commit=False)


def _determine_status(outcomes: list[FirehosePageOutcome]) -> FirehoseRunStatus:
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
    outcomes: list[FirehosePageOutcome],
    checkpoint: FirehoseCheckpointState,
) -> Path | None:
    if runtime_dir is None:
        return None

    artifact_dir = runtime_dir / "firehose" / "ingestion-runs"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    artifact_path = artifact_dir / f"{timestamp}.json"
    artifact_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": status.value,
                "checkpoint": {
                    "active_mode": (
                        checkpoint.active_mode.value
                        if checkpoint.active_mode is not None
                        else None
                    ),
                    "next_page": checkpoint.next_page,
                    "pages_processed_in_run": checkpoint.pages_processed_in_run,
                    "resume_required": checkpoint.resume_required,
                    "run_started_at": (
                        checkpoint.run_started_at.isoformat()
                        if checkpoint.run_started_at is not None
                        else None
                    ),
                    "last_checkpointed_at": (
                        checkpoint.last_checkpointed_at.isoformat()
                        if checkpoint.last_checkpointed_at is not None
                        else None
                    ),
                    "anchors": {
                        "new": (
                            checkpoint.new_anchor_date.isoformat()
                            if checkpoint.new_anchor_date is not None
                            else None
                        ),
                        "trending": (
                            checkpoint.trending_anchor_date.isoformat()
                            if checkpoint.trending_anchor_date is not None
                            else None
                        ),
                    },
                },
                "outcomes": [
                    {
                        "mode": outcome.mode.value,
                        "page": outcome.page,
                        "anchor_date": outcome.anchor_date.isoformat(),
                        "fetched_count": outcome.fetched_count,
                        "inserted_count": outcome.inserted_count,
                        "skipped_count": outcome.skipped_count,
                        "error": outcome.error,
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


def _next_checkpoint(
    *,
    checkpoint: FirehoseCheckpointState,
    modes: tuple[FirehoseMode, ...],
    fetched_count: int,
    per_page: int,
    checkpointed_at: datetime,
    processed_pages: int,
) -> FirehoseCheckpointState:
    if checkpoint.active_mode is None:
        raise ValueError("Cannot advance Firehose progress without an active mode")
    if fetched_count >= per_page:
        return advance_firehose_progress(
            checkpoint,
            active_mode=checkpoint.active_mode,
            next_page=checkpoint.next_page + 1,
            checkpointed_at=checkpointed_at,
            pages_processed_in_run=processed_pages,
        )

    mode_index = modes.index(checkpoint.active_mode)
    if mode_index < len(modes) - 1:
        return advance_firehose_progress(
            checkpoint,
            active_mode=modes[mode_index + 1],
            next_page=1,
            checkpointed_at=checkpointed_at,
            pages_processed_in_run=0,
        )
    return clear_firehose_progress(checkpoint, checkpointed_at=checkpointed_at)


def _checkpoint_after_mode_page_budget(
    *,
    checkpoint: FirehoseCheckpointState,
    modes: tuple[FirehoseMode, ...],
    mode: FirehoseMode,
    processed_pages: int,
    pages: int,
) -> FirehoseCheckpointState:
    if processed_pages < pages or checkpoint.active_mode is not mode:
        return checkpoint

    mode_index = modes.index(mode)
    if mode_index >= len(modes) - 1:
        return clear_firehose_progress(
            checkpoint,
            checkpointed_at=checkpoint.last_checkpointed_at,
        )

    return advance_firehose_progress(
        checkpoint,
        active_mode=modes[mode_index + 1],
        next_page=1,
        checkpointed_at=checkpoint.last_checkpointed_at,
        pages_processed_in_run=0,
    )


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()

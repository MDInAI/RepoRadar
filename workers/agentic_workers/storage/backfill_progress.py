from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import math

from sqlmodel import Session

from agentic_workers.storage.backend_models import BackfillProgress, exhausted_backfill_boundary


DEFAULT_SOURCE_PROVIDER = "github"


@dataclass(frozen=True, slots=True)
class BackfillCheckpointState:
    source_provider: str
    window_start_date: date
    created_before_boundary: date
    created_before_cursor: datetime | None
    next_page: int
    exhausted: bool
    last_checkpointed_at: datetime | None
    resume_required: bool = False
    pages_processed_in_run: int = 0


def initialize_backfill_progress(
    *,
    today: date,
    window_days: int,
    min_created_date: date,
    source_provider: str = DEFAULT_SOURCE_PROVIDER,
) -> BackfillCheckpointState:
    """Create the first durable checkpoint for a Backfill run."""
    _validate_window_days(window_days)

    if today <= min_created_date:
        return BackfillCheckpointState(
            source_provider=source_provider,
            window_start_date=min_created_date,
            created_before_boundary=exhausted_backfill_boundary(min_created_date),
            created_before_cursor=None,
            next_page=1,
            exhausted=True,
            last_checkpointed_at=None,
            resume_required=False,
            pages_processed_in_run=0,
        )

    window_end_date = today - timedelta(days=1)
    window_start_date = max(min_created_date, window_end_date - timedelta(days=window_days - 1))
    return BackfillCheckpointState(
        source_provider=source_provider,
        window_start_date=window_start_date,
        created_before_boundary=today,
        created_before_cursor=None,
        next_page=1,
        exhausted=False,
        last_checkpointed_at=None,
        resume_required=True,
        pages_processed_in_run=0,
    )


def load_backfill_progress(
    session: Session,
    *,
    source_provider: str = DEFAULT_SOURCE_PROVIDER,
) -> BackfillCheckpointState | None:
    """Load the persisted Backfill checkpoint for a provider, if one exists."""
    record = session.get(BackfillProgress, source_provider)
    if record is None:
        return None
    return BackfillCheckpointState(
        source_provider=record.source_provider,
        window_start_date=record.window_start_date,
        created_before_boundary=record.created_before_boundary,
        created_before_cursor=record.created_before_cursor,
        next_page=record.next_page,
        exhausted=record.exhausted,
        last_checkpointed_at=record.last_checkpointed_at,
        resume_required=record.resume_required,
        pages_processed_in_run=record.pages_processed_in_run,
    )


def advance_backfill_progress(
    progress: BackfillCheckpointState,
    *,
    repositories_fetched: int,
    oldest_created_at: datetime | None,
    batch_has_mixed_timestamps: bool,
    per_page: int,
    window_days: int,
    min_created_date: date,
    checkpointed_at: datetime | None = None,
    pages_processed_in_run: int | None = None,
) -> BackfillCheckpointState:
    """Advance a Backfill checkpoint after a batch has been fetched and persisted."""
    _validate_window_days(window_days)

    if progress.exhausted:
        return progress

    checkpoint_at = checkpointed_at or datetime.now(timezone.utc)
    processed_pages = (
        progress.pages_processed_in_run
        if pages_processed_in_run is None
        else pages_processed_in_run
    )
    if (
        repositories_fetched >= per_page
        and oldest_created_at is not None
        and oldest_created_at <= _effective_upper_bound(progress)
    ):
        next_page = 1
        safe_page_limit = max(1, math.ceil(1000 / per_page))
        next_cursor = oldest_created_at

        if progress.created_before_cursor == oldest_created_at:
            next_page = progress.next_page + 1
        elif progress.created_before_cursor is not None and batch_has_mixed_timestamps:
            next_cursor = progress.created_before_cursor
            next_page = progress.next_page + 1
        elif not batch_has_mixed_timestamps:
            next_page = 2

        if next_page > safe_page_limit:
            return BackfillCheckpointState(
                source_provider=progress.source_provider,
                window_start_date=progress.window_start_date,
                created_before_boundary=progress.created_before_boundary,
                created_before_cursor=next_cursor - timedelta(seconds=1),
                next_page=1,
                exhausted=False,
                last_checkpointed_at=checkpoint_at,
                resume_required=True,
                pages_processed_in_run=processed_pages,
            )

        return BackfillCheckpointState(
            source_provider=progress.source_provider,
            window_start_date=progress.window_start_date,
            created_before_boundary=progress.created_before_boundary,
            created_before_cursor=next_cursor,
            next_page=next_page,
            exhausted=False,
            last_checkpointed_at=checkpoint_at,
            resume_required=True,
            pages_processed_in_run=processed_pages,
        )

    next_boundary = progress.window_start_date
    if next_boundary <= min_created_date:
        return BackfillCheckpointState(
            source_provider=progress.source_provider,
            window_start_date=min_created_date,
            created_before_boundary=exhausted_backfill_boundary(min_created_date),
            created_before_cursor=None,
            next_page=1,
            exhausted=True,
            last_checkpointed_at=checkpoint_at,
            resume_required=True,
            pages_processed_in_run=processed_pages,
        )

    next_window_end_date = next_boundary - timedelta(days=1)
    next_window_start_date = max(
        min_created_date,
        next_window_end_date - timedelta(days=window_days - 1),
    )
    return BackfillCheckpointState(
        source_provider=progress.source_provider,
        window_start_date=next_window_start_date,
        created_before_boundary=next_boundary,
        created_before_cursor=None,
        next_page=1,
        exhausted=False,
        last_checkpointed_at=checkpoint_at,
        resume_required=True,
        pages_processed_in_run=processed_pages,
    )


def save_backfill_progress(
    session: Session,
    progress: BackfillCheckpointState,
    *,
    commit: bool = True,
) -> None:
    """Persist the latest Backfill checkpoint state."""
    record = session.get(BackfillProgress, progress.source_provider)
    if record is None:
        record = BackfillProgress(
            source_provider=progress.source_provider,
            window_start_date=progress.window_start_date,
            created_before_boundary=progress.created_before_boundary,
            created_before_cursor=progress.created_before_cursor,
            next_page=progress.next_page,
            pages_processed_in_run=progress.pages_processed_in_run,
            exhausted=progress.exhausted,
            resume_required=progress.resume_required,
            last_checkpointed_at=progress.last_checkpointed_at,
            updated_at=datetime.now(timezone.utc),
        )
        session.add(record)
    else:
        record.window_start_date = progress.window_start_date
        record.created_before_boundary = progress.created_before_boundary
        record.created_before_cursor = progress.created_before_cursor
        record.next_page = progress.next_page
        record.pages_processed_in_run = progress.pages_processed_in_run
        record.exhausted = progress.exhausted
        record.resume_required = progress.resume_required
        record.last_checkpointed_at = progress.last_checkpointed_at
        record.updated_at = datetime.now(timezone.utc)

    if commit:
        session.commit()


def _effective_upper_bound(progress: BackfillCheckpointState) -> datetime:
    return progress.created_before_cursor or datetime.combine(
        progress.created_before_boundary,
        time.min,
        tzinfo=timezone.utc,
    )


def _validate_window_days(window_days: int) -> None:
    if window_days <= 0:
        raise ValueError("window_days must be greater than zero")

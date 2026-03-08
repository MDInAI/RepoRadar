from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

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


def initialize_backfill_progress(
    *,
    today: date,
    window_days: int,
    min_created_date: date,
    source_provider: str = DEFAULT_SOURCE_PROVIDER,
) -> BackfillCheckpointState:
    if today <= min_created_date:
        return BackfillCheckpointState(
            source_provider=source_provider,
            window_start_date=min_created_date,
            created_before_boundary=exhausted_backfill_boundary(min_created_date),
            created_before_cursor=None,
            next_page=1,
            exhausted=True,
            last_checkpointed_at=None,
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
    )


def load_backfill_progress(
    session: Session,
    *,
    source_provider: str = DEFAULT_SOURCE_PROVIDER,
) -> BackfillCheckpointState | None:
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
    )


def advance_backfill_progress(
    progress: BackfillCheckpointState,
    *,
    repositories_fetched: int,
    oldest_created_at: datetime | None,
    has_results_newer_than_oldest: bool,
    per_page: int,
    window_days: int,
    min_created_date: date,
    checkpointed_at: datetime | None = None,
) -> BackfillCheckpointState:
    if progress.exhausted:
        return progress

    checkpoint_at = checkpointed_at or datetime.now(timezone.utc)
    if (
        repositories_fetched >= per_page
        and oldest_created_at is not None
        and oldest_created_at <= _effective_upper_bound(progress)
    ):
        next_page = 1
        
        safe_page_limit = 1000 // per_page
        
        if progress.created_before_cursor == oldest_created_at:
            next_page = progress.next_page + 1
        elif not has_results_newer_than_oldest:
            next_page = 2
            
        if next_page > safe_page_limit:
            # We've hit the GitHub pagination cap for this exact second timestamp!
            # We must aggressively shrink the window to break out of the stall.
            # We skip any remaining repositories in this exact second and move to the previous second.
            return BackfillCheckpointState(
                source_provider=progress.source_provider,
                window_start_date=progress.window_start_date,
                created_before_boundary=progress.created_before_boundary,
                created_before_cursor=oldest_created_at - timedelta(seconds=1),
                next_page=1,
                exhausted=False,
                last_checkpointed_at=checkpoint_at,
            )

        return BackfillCheckpointState(
            source_provider=progress.source_provider,
            window_start_date=progress.window_start_date,
            created_before_boundary=progress.created_before_boundary,
            created_before_cursor=oldest_created_at,
            next_page=next_page,
            exhausted=False,
            last_checkpointed_at=checkpoint_at,
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
    )


def save_backfill_progress(
    session: Session,
    progress: BackfillCheckpointState,
    *,
    commit: bool = True,
) -> None:
    record = session.get(BackfillProgress, progress.source_provider)
    if record is None:
        record = BackfillProgress(
            source_provider=progress.source_provider,
            window_start_date=progress.window_start_date,
            created_before_boundary=progress.created_before_boundary,
            created_before_cursor=progress.created_before_cursor,
            next_page=progress.next_page,
            exhausted=progress.exhausted,
            last_checkpointed_at=progress.last_checkpointed_at,
            updated_at=datetime.now(timezone.utc),
        )
        session.add(record)
    else:
        record.window_start_date = progress.window_start_date
        record.created_before_boundary = progress.created_before_boundary
        record.created_before_cursor = progress.created_before_cursor
        record.next_page = progress.next_page
        record.exhausted = progress.exhausted
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

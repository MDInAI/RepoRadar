"""Checkpoint persistence for IdeaScout searches.

Mirrors the backfill_progress module but keyed by (idea_search_id, query_index)
instead of source_provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import math

from sqlmodel import Session, select

from agentic_workers.storage.backend_models import IdeaSearchProgress


@dataclass(frozen=True, slots=True)
class IdeaSearchCheckpointState:
    idea_search_id: int
    query_index: int
    window_start_date: date
    created_before_boundary: date
    created_before_cursor: datetime | None
    next_page: int
    exhausted: bool
    last_checkpointed_at: datetime | None
    resume_required: bool = False
    pages_processed_in_run: int = 0
    consecutive_errors: int = 0
    last_error: str | None = None


def initialize_idea_search_progress(
    *,
    idea_search_id: int,
    query_index: int,
    today: date,
    window_days: int,
    min_created_date: date,
) -> IdeaSearchCheckpointState:
    """Create the first checkpoint for an IdeaScout query."""
    _validate_window_days(window_days)

    if today <= min_created_date:
        return IdeaSearchCheckpointState(
            idea_search_id=idea_search_id,
            query_index=query_index,
            window_start_date=min_created_date,
            created_before_boundary=min_created_date + timedelta(days=1),
            created_before_cursor=None,
            next_page=1,
            exhausted=True,
            last_checkpointed_at=None,
            resume_required=False,
            pages_processed_in_run=0,
        )

    window_end_date = today - timedelta(days=1)
    window_start_date = max(min_created_date, window_end_date - timedelta(days=window_days - 1))
    return IdeaSearchCheckpointState(
        idea_search_id=idea_search_id,
        query_index=query_index,
        window_start_date=window_start_date,
        created_before_boundary=today,
        created_before_cursor=None,
        next_page=1,
        exhausted=False,
        last_checkpointed_at=None,
        resume_required=True,
        pages_processed_in_run=0,
    )


def initialize_forward_watch_progress(
    *,
    idea_search_id: int,
    query_index: int,
    today: date,
) -> IdeaSearchCheckpointState:
    """Create the first checkpoint for a forward-watching IdeaSearch.

    Forward watches search for repos created from today onward.
    """
    return IdeaSearchCheckpointState(
        idea_search_id=idea_search_id,
        query_index=query_index,
        window_start_date=today - timedelta(days=1),
        created_before_boundary=today + timedelta(days=1),
        created_before_cursor=None,
        next_page=1,
        exhausted=False,
        last_checkpointed_at=None,
        resume_required=False,
        pages_processed_in_run=0,
    )


def load_idea_search_progress(
    session: Session,
    *,
    idea_search_id: int,
    query_index: int,
) -> IdeaSearchCheckpointState | None:
    """Load a persisted checkpoint for a specific search + query."""
    stmt = (
        select(IdeaSearchProgress)
        .where(IdeaSearchProgress.idea_search_id == idea_search_id)
        .where(IdeaSearchProgress.query_index == query_index)
    )
    record = session.exec(stmt).first()
    if record is None:
        return None
    return IdeaSearchCheckpointState(
        idea_search_id=record.idea_search_id,
        query_index=record.query_index,
        window_start_date=record.window_start_date,
        created_before_boundary=record.created_before_boundary,
        created_before_cursor=record.created_before_cursor,
        next_page=record.next_page,
        exhausted=record.exhausted,
        last_checkpointed_at=record.last_checkpointed_at,
        resume_required=record.resume_required,
        pages_processed_in_run=record.pages_processed_in_run,
        consecutive_errors=getattr(record, "consecutive_errors", 0) or 0,
        last_error=getattr(record, "last_error", None),
    )


def load_all_idea_search_progress(
    session: Session,
    *,
    idea_search_id: int,
) -> list[IdeaSearchCheckpointState]:
    """Load all per-query checkpoints for a given IdeaSearch."""
    stmt = (
        select(IdeaSearchProgress)
        .where(IdeaSearchProgress.idea_search_id == idea_search_id)
        .order_by(IdeaSearchProgress.query_index)
    )
    records = session.exec(stmt).all()
    return [
        IdeaSearchCheckpointState(
            idea_search_id=r.idea_search_id,
            query_index=r.query_index,
            window_start_date=r.window_start_date,
            created_before_boundary=r.created_before_boundary,
            created_before_cursor=r.created_before_cursor,
            next_page=r.next_page,
            exhausted=r.exhausted,
            last_checkpointed_at=r.last_checkpointed_at,
            resume_required=r.resume_required,
            pages_processed_in_run=r.pages_processed_in_run,
            consecutive_errors=getattr(r, "consecutive_errors", 0) or 0,
            last_error=getattr(r, "last_error", None),
        )
        for r in records
    ]


def advance_idea_search_progress(
    progress: IdeaSearchCheckpointState,
    *,
    repositories_fetched: int,
    oldest_created_at: datetime | None,
    batch_has_mixed_timestamps: bool,
    per_page: int,
    window_days: int,
    min_created_date: date,
    checkpointed_at: datetime | None = None,
    pages_processed_in_run: int | None = None,
) -> IdeaSearchCheckpointState:
    """Advance an IdeaSearch checkpoint after a batch has been fetched."""
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
            return IdeaSearchCheckpointState(
                idea_search_id=progress.idea_search_id,
                query_index=progress.query_index,
                window_start_date=progress.window_start_date,
                created_before_boundary=progress.created_before_boundary,
                created_before_cursor=next_cursor - timedelta(seconds=1),
                next_page=1,
                exhausted=False,
                last_checkpointed_at=checkpoint_at,
                resume_required=True,
                pages_processed_in_run=processed_pages,
            )

        return IdeaSearchCheckpointState(
            idea_search_id=progress.idea_search_id,
            query_index=progress.query_index,
            window_start_date=progress.window_start_date,
            created_before_boundary=progress.created_before_boundary,
            created_before_cursor=next_cursor,
            next_page=next_page,
            exhausted=False,
            last_checkpointed_at=checkpoint_at,
            resume_required=True,
            pages_processed_in_run=processed_pages,
        )

    # Window exhausted — slide backward
    next_boundary = progress.window_start_date
    if next_boundary <= min_created_date:
        return IdeaSearchCheckpointState(
            idea_search_id=progress.idea_search_id,
            query_index=progress.query_index,
            window_start_date=min_created_date,
            created_before_boundary=min_created_date + timedelta(days=1),
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
    return IdeaSearchCheckpointState(
        idea_search_id=progress.idea_search_id,
        query_index=progress.query_index,
        window_start_date=next_window_start_date,
        created_before_boundary=next_boundary,
        created_before_cursor=None,
        next_page=1,
        exhausted=False,
        last_checkpointed_at=checkpoint_at,
        resume_required=True,
        pages_processed_in_run=processed_pages,
    )


def save_idea_search_progress(
    session: Session,
    progress: IdeaSearchCheckpointState,
    *,
    commit: bool = True,
) -> None:
    """Persist the latest IdeaSearch checkpoint state."""
    stmt = (
        select(IdeaSearchProgress)
        .where(IdeaSearchProgress.idea_search_id == progress.idea_search_id)
        .where(IdeaSearchProgress.query_index == progress.query_index)
    )
    record = session.exec(stmt).first()
    if record is None:
        record = IdeaSearchProgress(
            idea_search_id=progress.idea_search_id,
            query_index=progress.query_index,
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
        if hasattr(record, "consecutive_errors"):
            record.consecutive_errors = progress.consecutive_errors
        if hasattr(record, "last_error"):
            record.last_error = progress.last_error
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
        if hasattr(record, "consecutive_errors"):
            record.consecutive_errors = progress.consecutive_errors
        if hasattr(record, "last_error"):
            record.last_error = progress.last_error

    if commit:
        session.commit()


_MAX_CONSECUTIVE_ERRORS = 3


def record_idea_search_error(
    progress: IdeaSearchCheckpointState,
    *,
    error_message: str,
    window_days: int,
    min_created_date: date,
) -> IdeaSearchCheckpointState:
    """Record an error on the checkpoint and skip the current window after too many consecutive failures.

    After ``_MAX_CONSECUTIVE_ERRORS`` consecutive errors on the same window,
    the checkpoint slides backward to the next window so the search is not
    stuck forever on a query/window that always fails.
    """
    new_count = progress.consecutive_errors + 1
    short_error = (error_message or "unknown")[:500]
    now = datetime.now(timezone.utc)

    if new_count < _MAX_CONSECUTIVE_ERRORS:
        return IdeaSearchCheckpointState(
            idea_search_id=progress.idea_search_id,
            query_index=progress.query_index,
            window_start_date=progress.window_start_date,
            created_before_boundary=progress.created_before_boundary,
            created_before_cursor=progress.created_before_cursor,
            next_page=progress.next_page,
            exhausted=progress.exhausted,
            last_checkpointed_at=now,
            resume_required=progress.resume_required,
            pages_processed_in_run=progress.pages_processed_in_run,
            consecutive_errors=new_count,
            last_error=short_error,
        )

    # Too many consecutive errors — skip to next window
    _validate_window_days(window_days)
    next_boundary = progress.window_start_date
    if next_boundary <= min_created_date:
        return IdeaSearchCheckpointState(
            idea_search_id=progress.idea_search_id,
            query_index=progress.query_index,
            window_start_date=min_created_date,
            created_before_boundary=min_created_date + timedelta(days=1),
            created_before_cursor=None,
            next_page=1,
            exhausted=True,
            last_checkpointed_at=now,
            resume_required=False,
            pages_processed_in_run=progress.pages_processed_in_run,
            consecutive_errors=0,
            last_error=f"Skipped to exhaustion after {new_count} errors: {short_error}",
        )

    next_window_end_date = next_boundary - timedelta(days=1)
    next_window_start_date = max(
        min_created_date,
        next_window_end_date - timedelta(days=window_days - 1),
    )
    return IdeaSearchCheckpointState(
        idea_search_id=progress.idea_search_id,
        query_index=progress.query_index,
        window_start_date=next_window_start_date,
        created_before_boundary=next_boundary,
        created_before_cursor=None,
        next_page=1,
        exhausted=False,
        last_checkpointed_at=now,
        resume_required=True,
        pages_processed_in_run=progress.pages_processed_in_run,
        consecutive_errors=0,
        last_error=f"Skipped window after {new_count} errors: {short_error}",
    )


# --- internal helpers ---


def _effective_upper_bound(progress: IdeaSearchCheckpointState) -> datetime:
    return progress.created_before_cursor or datetime.combine(
        progress.created_before_boundary,
        time.min,
        tzinfo=timezone.utc,
    )


def _validate_window_days(window_days: int) -> None:
    if window_days <= 0:
        raise ValueError("window_days must be greater than zero")

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlmodel import Session

from agentic_workers.providers.github_provider import FirehoseMode
from agentic_workers.storage.backend_models import FirehoseProgress, RepositoryFirehoseMode


DEFAULT_SOURCE_PROVIDER = "github"


@dataclass(frozen=True, slots=True)
class FirehoseCheckpointState:
    source_provider: str
    active_mode: FirehoseMode | None
    next_page: int
    new_anchor_date: date | None
    trending_anchor_date: date | None
    run_started_at: datetime | None
    resume_required: bool
    last_checkpointed_at: datetime | None
    pages_processed_in_run: int = 0


def initialize_firehose_progress(
    *,
    today: date | None = None,
    source_provider: str = DEFAULT_SOURCE_PROVIDER,
    active_mode: FirehoseMode = FirehoseMode.NEW,
    started_at: datetime | None = None,
) -> FirehoseCheckpointState:
    run_started_at = started_at or datetime.now(timezone.utc)
    active_today = today or run_started_at.date()
    return FirehoseCheckpointState(
        source_provider=source_provider,
        active_mode=active_mode,
        next_page=1,
        new_anchor_date=active_today - timedelta(days=1),
        trending_anchor_date=active_today - timedelta(days=7),
        run_started_at=run_started_at,
        resume_required=True,
        last_checkpointed_at=None,
        pages_processed_in_run=0,
    )


def load_firehose_progress(
    session: Session,
    *,
    source_provider: str = DEFAULT_SOURCE_PROVIDER,
) -> FirehoseCheckpointState | None:
    record = session.get(FirehoseProgress, source_provider)
    if record is None:
        return None
    return FirehoseCheckpointState(
        source_provider=record.source_provider,
        active_mode=(
            FirehoseMode(record.active_mode.value)
            if record.active_mode is not None
            else None
        ),
        next_page=record.next_page,
        new_anchor_date=record.new_anchor_date,
        trending_anchor_date=record.trending_anchor_date,
        run_started_at=record.run_started_at,
        resume_required=record.resume_required,
        last_checkpointed_at=record.last_checkpointed_at,
        pages_processed_in_run=record.pages_processed_in_run,
    )


def save_firehose_progress(
    session: Session,
    progress: FirehoseCheckpointState,
    *,
    commit: bool = True,
) -> None:
    record = session.get(FirehoseProgress, progress.source_provider)
    if record is None:
        record = FirehoseProgress(
            source_provider=progress.source_provider,
            active_mode=_to_record_mode(progress.active_mode),
            next_page=progress.next_page,
            pages_processed_in_run=progress.pages_processed_in_run,
            new_anchor_date=progress.new_anchor_date,
            trending_anchor_date=progress.trending_anchor_date,
            run_started_at=progress.run_started_at,
            resume_required=progress.resume_required,
            last_checkpointed_at=progress.last_checkpointed_at,
            updated_at=datetime.now(timezone.utc),
        )
        session.add(record)
    else:
        record.active_mode = _to_record_mode(progress.active_mode)
        record.next_page = progress.next_page
        record.pages_processed_in_run = progress.pages_processed_in_run
        record.new_anchor_date = progress.new_anchor_date
        record.trending_anchor_date = progress.trending_anchor_date
        record.run_started_at = progress.run_started_at
        record.resume_required = progress.resume_required
        record.last_checkpointed_at = progress.last_checkpointed_at
        record.updated_at = datetime.now(timezone.utc)

    if commit:
        session.commit()


def advance_firehose_progress(
    progress: FirehoseCheckpointState,
    *,
    active_mode: FirehoseMode,
    next_page: int,
    checkpointed_at: datetime | None = None,
    pages_processed_in_run: int | None = None,
) -> FirehoseCheckpointState:
    return FirehoseCheckpointState(
        source_provider=progress.source_provider,
        active_mode=active_mode,
        next_page=next_page,
        new_anchor_date=progress.new_anchor_date,
        trending_anchor_date=progress.trending_anchor_date,
        run_started_at=progress.run_started_at,
        resume_required=True,
        last_checkpointed_at=checkpointed_at or datetime.now(timezone.utc),
        pages_processed_in_run=(
            progress.pages_processed_in_run
            if pages_processed_in_run is None
            else pages_processed_in_run
        ),
    )


def clear_firehose_progress(
    progress: FirehoseCheckpointState,
    *,
    checkpointed_at: datetime | None = None,
) -> FirehoseCheckpointState:
    return FirehoseCheckpointState(
        source_provider=progress.source_provider,
        active_mode=None,
        next_page=1,
        new_anchor_date=None,
        trending_anchor_date=None,
        run_started_at=None,
        resume_required=False,
        last_checkpointed_at=checkpointed_at or datetime.now(timezone.utc),
        pages_processed_in_run=0,
    )


def anchor_for_mode(
    progress: FirehoseCheckpointState,
    mode: FirehoseMode,
) -> date:
    anchor = progress.new_anchor_date if mode is FirehoseMode.NEW else progress.trending_anchor_date
    if anchor is None:
        raise ValueError(
            f"Missing persisted anchor for Firehose mode {mode.value}. "
            f"This indicates corrupted checkpoint state "
            f"(active_mode={progress.active_mode}, resume_required={progress.resume_required}). "
            "Consider clearing the firehose_progress table and restarting."
        )
    return anchor


def _to_record_mode(mode: FirehoseMode | None) -> RepositoryFirehoseMode | None:
    if mode is None:
        return None
    return RepositoryFirehoseMode(mode.value)

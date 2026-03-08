from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import agentic_workers.jobs.backfill_job as backfill_job_module
from agentic_workers.jobs.backfill_job import BackfillRunStatus, run_backfill_job
from agentic_workers.providers.github_provider import DiscoveredRepository
from agentic_workers.storage.backfill_progress import BackfillCheckpointState
from agentic_workers.storage.repository_intake import IntakePersistenceResult


class StubSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _repository(
    repository_id: int,
    *,
    created_at: datetime | None = None,
) -> DiscoveredRepository:
    return DiscoveredRepository(
        github_repository_id=repository_id,
        owner_login="octocat",
        repository_name=f"repo-{repository_id}",
        full_name=f"octocat/repo-{repository_id}",
        created_at=created_at or datetime(2026, 2, 15, repository_id % 24, 0, tzinfo=timezone.utc),
    )


def test_backfill_job_uses_stored_checkpoint_when_resuming(tmp_path: Path) -> None:
    session = StubSession()
    discover_calls: list[tuple[date, date, datetime | None, int, int]] = []
    saved_checkpoints: list[BackfillCheckpointState] = []
    initial_checkpoint = BackfillCheckpointState(
        source_provider="github",
        window_start_date=date(2026, 2, 1),
        created_before_boundary=date(2026, 3, 1),
        created_before_cursor=None,
        next_page=3,
        exhausted=False,
        last_checkpointed_at=None,
    )

    class Provider:
        def discover_backfill(
            self,
            *,
            window_start_date: date,
            created_before_boundary: date,
            created_before_cursor: datetime | None = None,
            per_page: int = 25,
            page: int = 1,
        ) -> list[DiscoveredRepository]:
            discover_calls.append(
                (window_start_date, created_before_boundary, created_before_cursor, per_page, page)
            )
            return [_repository(101), _repository(102)]

    result = run_backfill_job(
        session=session,  # type: ignore[arg-type]
        provider=Provider(),
        runtime_dir=tmp_path,
        pacing_seconds=5,
        per_page=2,
        pages=1,
        window_days=30,
        min_created_date=date(2008, 1, 1),
        sleep_fn=lambda _seconds: None,
        load_progress=lambda _session: initial_checkpoint,
        save_progress=lambda _session, checkpoint: saved_checkpoints.append(checkpoint),
        persist_batch=lambda _session, repositories: IntakePersistenceResult(
            inserted_count=len(repositories),
            skipped_count=0,
        ),
    )

    assert discover_calls == [(date(2026, 2, 1), date(2026, 3, 1), None, 2, 3)]
    assert session.commits == 1
    assert session.rollbacks == 0
    assert result.status is BackfillRunStatus.SUCCESS
    assert saved_checkpoints[0].next_page == 1
    assert saved_checkpoints[0].created_before_boundary == date(2026, 3, 1)
    assert saved_checkpoints[0].created_before_cursor == datetime(
        2026,
        2,
        15,
        5,
        0,
        tzinfo=timezone.utc,
    )


def test_backfill_job_moves_to_older_window_after_partial_page(tmp_path: Path) -> None:
    session = StubSession()
    saved_checkpoints: list[BackfillCheckpointState] = []
    initial_checkpoint = BackfillCheckpointState(
        source_provider="github",
        window_start_date=date(2026, 2, 1),
        created_before_boundary=date(2026, 3, 1),
        created_before_cursor=datetime(2026, 2, 2, 0, 0, tzinfo=timezone.utc),
        next_page=1,
        exhausted=False,
        last_checkpointed_at=datetime.now(timezone.utc),
    )

    class Provider:
        def discover_backfill(
            self,
            *,
            window_start_date: date,
            created_before_boundary: date,
            created_before_cursor: datetime | None = None,
            per_page: int = 25,
            page: int = 1,
        ) -> list[DiscoveredRepository]:
            return [_repository(201)]

    result = run_backfill_job(
        session=session,  # type: ignore[arg-type]
        provider=Provider(),
        runtime_dir=tmp_path,
        pacing_seconds=5,
        per_page=2,
        pages=1,
        window_days=30,
        min_created_date=date(2008, 1, 1),
        sleep_fn=lambda _seconds: None,
        load_progress=lambda _session: initial_checkpoint,
        save_progress=lambda _session, checkpoint: saved_checkpoints.append(checkpoint),
        persist_batch=lambda _session, repositories: IntakePersistenceResult(
            inserted_count=len(repositories),
            skipped_count=0,
        ),
    )

    assert result.status is BackfillRunStatus.SUCCESS
    assert saved_checkpoints[0].next_page == 1
    assert saved_checkpoints[0].created_before_boundary == date(2026, 2, 1)
    assert saved_checkpoints[0].created_before_cursor is None
    assert saved_checkpoints[0].window_start_date == date(2026, 1, 2)


def test_backfill_job_does_not_advance_checkpoint_after_persist_failure(tmp_path: Path) -> None:
    session = StubSession()
    saved_checkpoints: list[BackfillCheckpointState] = []
    initial_checkpoint = BackfillCheckpointState(
        source_provider="github",
        window_start_date=date(2026, 2, 1),
        created_before_boundary=date(2026, 3, 1),
        created_before_cursor=None,
        next_page=1,
        exhausted=False,
        last_checkpointed_at=None,
    )

    class Provider:
        def discover_backfill(
            self,
            *,
            window_start_date: date,
            created_before_boundary: date,
            created_before_cursor: datetime | None = None,
            per_page: int = 25,
            page: int = 1,
        ) -> list[DiscoveredRepository]:
            return [_repository(301)]

    result = run_backfill_job(
        session=session,  # type: ignore[arg-type]
        provider=Provider(),
        runtime_dir=tmp_path,
        pacing_seconds=5,
        per_page=2,
        pages=1,
        window_days=30,
        min_created_date=date(2008, 1, 1),
        sleep_fn=lambda _seconds: None,
        load_progress=lambda _session: initial_checkpoint,
        save_progress=lambda _session, checkpoint: saved_checkpoints.append(checkpoint),
        persist_batch=lambda _session, repositories: (_ for _ in ()).throw(
            RuntimeError("queue write failed")
        ),
    )

    assert result.status is BackfillRunStatus.FAILED
    assert result.outcomes[0].error == "queue write failed"
    assert session.commits == 0
    assert session.rollbacks == 1
    assert saved_checkpoints == []


def test_backfill_job_keeps_page_cursor_for_equal_timestamp_spillover(tmp_path: Path) -> None:
    session = StubSession()
    discover_calls: list[tuple[date, date, datetime | None, int, int]] = []
    saved_checkpoints: list[BackfillCheckpointState] = []
    same_timestamp = datetime(2026, 2, 15, 5, 0, tzinfo=timezone.utc)
    initial_checkpoint = BackfillCheckpointState(
        source_provider="github",
        window_start_date=date(2026, 2, 1),
        created_before_boundary=date(2026, 3, 1),
        created_before_cursor=None,
        next_page=1,
        exhausted=False,
        last_checkpointed_at=None,
    )

    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        def discover_backfill(
            self,
            *,
            window_start_date: date,
            created_before_boundary: date,
            created_before_cursor: datetime | None = None,
            per_page: int = 25,
            page: int = 1,
        ) -> list[DiscoveredRepository]:
            self.calls += 1
            discover_calls.append(
                (window_start_date, created_before_boundary, created_before_cursor, per_page, page)
            )
            if self.calls == 1:
                return [
                    _repository(401, created_at=same_timestamp),
                    _repository(402, created_at=same_timestamp),
                ]
            return [_repository(403, created_at=datetime(2026, 2, 15, 4, 0, tzinfo=timezone.utc))]

    provider = Provider()

    first_result = run_backfill_job(
        session=session,  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=5,
        per_page=2,
        pages=1,
        window_days=30,
        min_created_date=date(2008, 1, 1),
        sleep_fn=lambda _seconds: None,
        load_progress=lambda _session: initial_checkpoint,
        save_progress=lambda _session, checkpoint: saved_checkpoints.append(checkpoint),
        persist_batch=lambda _session, repositories: IntakePersistenceResult(
            inserted_count=len(repositories),
            skipped_count=0,
        ),
    )

    second_result = run_backfill_job(
        session=session,  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=5,
        per_page=2,
        pages=1,
        window_days=30,
        min_created_date=date(2008, 1, 1),
        sleep_fn=lambda _seconds: None,
        load_progress=lambda _session: saved_checkpoints[-1],
        save_progress=lambda _session, checkpoint: saved_checkpoints.append(checkpoint),
        persist_batch=lambda _session, repositories: IntakePersistenceResult(
            inserted_count=len(repositories),
            skipped_count=0,
        ),
    )

    assert first_result.status is BackfillRunStatus.SUCCESS
    assert second_result.status is BackfillRunStatus.SUCCESS
    assert discover_calls == [
        (date(2026, 2, 1), date(2026, 3, 1), None, 2, 1),
        (date(2026, 2, 1), date(2026, 3, 1), same_timestamp, 2, 2),
    ]
    assert saved_checkpoints[0].created_before_cursor == same_timestamp
    assert saved_checkpoints[0].next_page == 2


def test_backfill_job_defaults_today_from_utc_clock(monkeypatch, tmp_path: Path) -> None:
    session = StubSession()
    discover_calls: list[tuple[date, date]] = []
    monkeypatch.setattr(backfill_job_module, "_utc_today", lambda: date(2026, 3, 8))

    class Provider:
        def discover_backfill(
            self,
            *,
            window_start_date: date,
            created_before_boundary: date,
            created_before_cursor: datetime | None = None,
            per_page: int = 25,
            page: int = 1,
        ) -> list[DiscoveredRepository]:
            discover_calls.append((window_start_date, created_before_boundary))
            return []

    result = run_backfill_job(
        session=session,  # type: ignore[arg-type]
        provider=Provider(),
        runtime_dir=tmp_path,
        pacing_seconds=5,
        per_page=2,
        pages=1,
        window_days=30,
        min_created_date=date(2008, 1, 1),
        sleep_fn=lambda _seconds: None,
        load_progress=lambda _session: None,
        save_progress=lambda _session, _checkpoint: None,
        persist_batch=lambda _session, repositories: IntakePersistenceResult(
            inserted_count=len(repositories),
            skipped_count=0,
        ),
    )

    assert result.status is BackfillRunStatus.SUCCESS
    assert discover_calls == [(date(2026, 2, 6), date(2026, 3, 8))]

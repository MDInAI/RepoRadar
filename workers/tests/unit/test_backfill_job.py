from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import agentic_workers.jobs.backfill_job as backfill_job_module
from agentic_workers.jobs.backfill_job import BackfillRunStatus, run_backfill_job
from agentic_workers.core.pause_policy import PauseDecision
from agentic_workers.providers.github_provider import (
    DiscoveredRepository,
    GitHubProviderError,
    GitHubRateLimitError,
)
from agentic_workers.storage.backfill_progress import (
    BackfillCheckpointState,
    advance_backfill_progress,
)
from agentic_workers.storage.backend_models import FailureClassification
from agentic_workers.storage.repository_intake import IntakePersistenceResult


class StubSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def add(self, _value: object) -> None:
        return None

    def flush(self) -> None:
        return None

    def exec(self, _statement: object) -> None:
        return None


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
        resume_required=True,
        pages_processed_in_run=2,
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
        pages=3,
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
    # 2 commits: 1 for the page processing + 1 for clearing resume_required
    assert session.commits == 2
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
    assert session.commits == 1
    assert session.rollbacks == 1
    assert saved_checkpoints == []


def test_backfill_job_unexpected_runtime_failures_pause_the_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = StubSession()
    emitted_events: list[dict[str, object]] = []
    pause_calls: list[tuple[PauseDecision, int | None]] = []
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
            del window_start_date, created_before_boundary, created_before_cursor, per_page, page
            raise RuntimeError("unexpected backfill crash")

    def fake_emit_failure_event(_session: object, **kwargs: object) -> int:
        emitted_events.append(kwargs)
        return len(emitted_events)

    monkeypatch.setattr(backfill_job_module, "emit_failure_event", fake_emit_failure_event)
    monkeypatch.setattr(
        backfill_job_module,
        "execute_pause",
        lambda _session, decision, event_id: pause_calls.append((decision, event_id)),
    )

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
    )

    assert result.status is BackfillRunStatus.FAILED
    assert [event["event_type"] for event in emitted_events] == [
        "repository_discovery_failed",
        "agent_paused",
    ]
    assert emitted_events[0]["classification"] is FailureClassification.BLOCKING
    assert pause_calls
    assert pause_calls[0][0].affected_agents == ["backfill"]
    assert pause_calls[0][1] == 1
    assert session.rollbacks == 1
    assert session.commits == 1


def test_backfill_job_rolls_back_when_pause_emission_fails_for_provider_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = StubSession()
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
            del window_start_date, created_before_boundary, created_before_cursor, per_page, page
            raise GitHubProviderError("github transport failed")

    monkeypatch.setattr(
        backfill_job_module,
        "emit_failure_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("event sink failed")),
    )

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
    )

    assert result.status is BackfillRunStatus.FAILED
    assert session.rollbacks == 2
    assert session.commits == 0


def test_backfill_job_returns_skipped_paused_when_agent_is_paused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backfill_job_module, "is_agent_paused", lambda *_args, **_kwargs: True)

    class Provider:
        def discover_backfill(self, **_kwargs: object) -> list[DiscoveredRepository]:
            raise AssertionError("discover_backfill should not run while paused")

    result = run_backfill_job(
        session=StubSession(),  # type: ignore[arg-type]
        provider=Provider(),
        runtime_dir=tmp_path,
        pacing_seconds=5,
        per_page=2,
        pages=1,
        window_days=30,
        min_created_date=date(2008, 1, 1),
        sleep_fn=lambda _seconds: None,
        load_progress=lambda _session: None,
    )

    assert result.status is BackfillRunStatus.SKIPPED_PAUSED
    assert result.outcomes == []


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


def test_advance_backfill_progress_keeps_last_reachable_page_when_per_page_does_not_divide_1000() -> None:
    same_timestamp = datetime(2026, 2, 15, 5, 0, tzinfo=timezone.utc)
    checkpoint = BackfillCheckpointState(
        source_provider="github",
        window_start_date=date(2026, 2, 1),
        created_before_boundary=date(2026, 3, 1),
        created_before_cursor=same_timestamp,
        next_page=3,
        exhausted=False,
        last_checkpointed_at=None,
    )

    next_checkpoint = advance_backfill_progress(
        checkpoint,
        repositories_fetched=300,
        oldest_created_at=same_timestamp,
        batch_has_mixed_timestamps=False,
        per_page=300,
        window_days=30,
        min_created_date=date(2008, 1, 1),
    )

    assert next_checkpoint.created_before_cursor == same_timestamp
    assert next_checkpoint.next_page == 4


def test_advance_backfill_progress_shrinks_cursor_after_reaching_safe_page_limit() -> None:
    same_timestamp = datetime(2026, 2, 15, 5, 0, tzinfo=timezone.utc)
    checkpoint = BackfillCheckpointState(
        source_provider="github",
        window_start_date=date(2026, 2, 1),
        created_before_boundary=date(2026, 3, 1),
        created_before_cursor=same_timestamp,
        next_page=4,
        exhausted=False,
        last_checkpointed_at=None,
    )

    next_checkpoint = advance_backfill_progress(
        checkpoint,
        repositories_fetched=300,
        oldest_created_at=same_timestamp,
        batch_has_mixed_timestamps=False,
        per_page=300,
        window_days=30,
        min_created_date=date(2008, 1, 1),
    )

    assert next_checkpoint.created_before_cursor == datetime(
        2026,
        2,
        15,
        4,
        59,
        59,
        tzinfo=timezone.utc,
    )
    assert next_checkpoint.next_page == 1


def test_backfill_job_sleeps_for_rate_limit_backoff_before_stopping(tmp_path: Path) -> None:
    session = StubSession()
    sleep_calls: list[int] = []
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
            raise GitHubRateLimitError(status_code=429, retry_after_seconds=120)

    result = run_backfill_job(
        session=session,  # type: ignore[arg-type]
        provider=Provider(),
        runtime_dir=tmp_path,
        pacing_seconds=5,
        per_page=2,
        pages=1,
        window_days=30,
        min_created_date=date(2008, 1, 1),
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
        load_progress=lambda _session: initial_checkpoint,
    )

    assert result.status is BackfillRunStatus.FAILED
    assert result.outcomes[0].error == "GitHub rate limit exceeded with status 429; retry after 120s"
    assert sleep_calls == [120]
    assert session.commits == 1
    assert session.rollbacks == 1


def test_advance_backfill_progress_preserves_cursor_pagination_for_mixed_timestamp_page() -> None:
    current_cursor = datetime(2026, 2, 15, 6, 0, tzinfo=timezone.utc)
    oldest_timestamp = datetime(2026, 2, 15, 5, 0, tzinfo=timezone.utc)
    checkpoint = BackfillCheckpointState(
        source_provider="github",
        window_start_date=date(2026, 2, 1),
        created_before_boundary=date(2026, 3, 1),
        created_before_cursor=current_cursor,
        next_page=2,
        exhausted=False,
        last_checkpointed_at=None,
    )

    next_checkpoint = advance_backfill_progress(
        checkpoint,
        repositories_fetched=100,
        oldest_created_at=oldest_timestamp,
        batch_has_mixed_timestamps=True,
        per_page=100,
        window_days=30,
        min_created_date=date(2008, 1, 1),
    )

    assert next_checkpoint.created_before_cursor == current_cursor
    assert next_checkpoint.next_page == 3


def test_backfill_job_respects_page_budget_on_resume(tmp_path: Path) -> None:
    """A resumed Backfill run must not overshoot the configured page cap.

    If pages=2 and the checkpoint says next_page=2 (page 1 was consumed before
    interruption), the resumed invocation should only process 1 more page — not
    a fresh budget of 2.
    """
    session = StubSession()
    discover_calls: list[tuple[date, date, datetime | None, int, int]] = []
    saved_checkpoints: list[BackfillCheckpointState] = []
    resumed_checkpoint = BackfillCheckpointState(
        source_provider="github",
        window_start_date=date(2026, 2, 1),
        created_before_boundary=date(2026, 3, 1),
        created_before_cursor=None,
        next_page=2,
        exhausted=False,
        last_checkpointed_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
        resume_required=True,
        pages_processed_in_run=1,
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
            return [_repository(501), _repository(502)]

    result = run_backfill_job(
        session=session,  # type: ignore[arg-type]
        provider=Provider(),
        runtime_dir=tmp_path,
        pacing_seconds=5,
        per_page=2,
        pages=2,
        window_days=30,
        min_created_date=date(2008, 1, 1),
        sleep_fn=lambda _seconds: None,
        load_progress=lambda _session: resumed_checkpoint,
        save_progress=lambda _session, checkpoint: saved_checkpoints.append(checkpoint),
        persist_batch=lambda _session, repositories: IntakePersistenceResult(
            inserted_count=len(repositories),
            skipped_count=0,
        ),
    )

    assert result.status is BackfillRunStatus.SUCCESS
    # Only 1 page should be processed — the remaining budget from a 2-page cap
    # with 1 page already consumed before the interruption.
    assert len(discover_calls) == 1
    assert discover_calls[0] == (date(2026, 2, 1), date(2026, 3, 1), None, 2, 2)
    # 2 commits: 1 for the resumed page + 1 to clear resume_required and reset
    # the per-run budget once that logical cycle finishes.
    assert session.commits == 2


def test_backfill_job_respects_remaining_budget_after_cursor_reset_on_resume(
    tmp_path: Path,
) -> None:
    session = StubSession()
    discover_calls: list[tuple[date, date, datetime | None, int, int]] = []
    resumed_checkpoint = BackfillCheckpointState(
        source_provider="github",
        window_start_date=date(2026, 2, 1),
        created_before_boundary=date(2026, 3, 1),
        created_before_cursor=datetime(2026, 2, 15, 5, 0, tzinfo=timezone.utc),
        next_page=1,
        exhausted=False,
        last_checkpointed_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
        resume_required=True,
        pages_processed_in_run=1,
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
            return [_repository(601), _repository(602)]

    result = run_backfill_job(
        session=session,  # type: ignore[arg-type]
        provider=Provider(),
        runtime_dir=tmp_path,
        pacing_seconds=5,
        per_page=2,
        pages=2,
        window_days=30,
        min_created_date=date(2008, 1, 1),
        sleep_fn=lambda _seconds: None,
        load_progress=lambda _session: resumed_checkpoint,
        save_progress=lambda _session, _checkpoint: None,
        persist_batch=lambda _session, repositories: IntakePersistenceResult(
            inserted_count=len(repositories),
            skipped_count=0,
        ),
    )

    assert result.status is BackfillRunStatus.SUCCESS
    assert discover_calls == [
        (
            date(2026, 2, 1),
            date(2026, 3, 1),
            datetime(2026, 2, 15, 5, 0, tzinfo=timezone.utc),
            2,
            1,
        )
    ]


def test_backfill_job_rejects_non_positive_window_days(tmp_path: Path) -> None:
    session = StubSession()

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
            raise AssertionError("provider should not be called when window_days is invalid")

    with pytest.raises(ValueError, match="window_days must be greater than zero"):
        run_backfill_job(
            session=session,  # type: ignore[arg-type]
            provider=Provider(),
            runtime_dir=tmp_path,
            pacing_seconds=5,
            per_page=2,
            pages=1,
            window_days=0,
            min_created_date=date(2008, 1, 1),
            sleep_fn=lambda _seconds: None,
        )


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

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

import agentic_workers.jobs.firehose_job as firehose_job_module
from sqlmodel import Session, create_engine, select

from agentic_workers.jobs.firehose_job import FirehoseRunResult, FirehoseRunStatus, run_firehose_job
from agentic_workers.providers.github_provider import (
    DiscoveredRepository,
    FirehoseMode,
    GitHubProviderError,
    GitHubRateLimitError,
)
from agentic_workers.core.pause_policy import PauseDecision
from agentic_workers.storage.backend_models import FailureClassification
from agentic_workers.storage.backend_models import RepositoryIntake, SQLModel
from agentic_workers.storage.firehose_progress import FirehoseCheckpointState
from agentic_workers.storage.repository_intake import IntakePersistenceResult


class StubProvider:
    def __init__(
        self,
        responses: dict[tuple[FirehoseMode, int], list[DiscoveredRepository] | Exception],
    ) -> None:
        self.responses = responses
        self.calls: list[tuple[FirehoseMode, date | None, int, int]] = []

    def discover(
        self,
        *,
        mode: FirehoseMode,
        anchor_date: date | None = None,
        per_page: int = 25,
        page: int = 1,
    ) -> list[DiscoveredRepository]:
        self.calls.append((mode, anchor_date, per_page, page))
        response = self.responses[(mode, page)]
        if isinstance(response, Exception):
            raise response
        return list(response)


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

    def get(self, _model: object, _identifier: object) -> None:
        return None


def _repository(mode: FirehoseMode, repository_id: int) -> DiscoveredRepository:
    return DiscoveredRepository(
        github_repository_id=repository_id,
        owner_login="octocat",
        repository_name=f"repo-{repository_id}",
        full_name=f"octocat/repo-{repository_id}",
        created_at=datetime(2026, 3, 7, repository_id % 24, 0, tzinfo=timezone.utc),
        firehose_discovery_mode=mode,
    )


def _fresh_checkpoint() -> FirehoseCheckpointState:
    return FirehoseCheckpointState(
        source_provider="github",
        active_mode=FirehoseMode.NEW,
        next_page=1,
        new_anchor_date=date(2026, 3, 7),
        trending_anchor_date=date(2026, 3, 1),
        run_started_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
        resume_required=True,
        last_checkpointed_at=None,
    )


def _persist_batch(
    _session: object,
    repositories: list[DiscoveredRepository],
    *,
    mode: FirehoseMode,
) -> IntakePersistenceResult:
    del mode
    return IntakePersistenceResult(inserted_count=len(repositories), skipped_count=0)


def _save_progress(_session: object, _checkpoint: FirehoseCheckpointState) -> None:
    return None


def test_firehose_job_paces_between_requests_and_records_page_outcomes(tmp_path: Path) -> None:
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): [_repository(FirehoseMode.NEW, 1)],
            (FirehoseMode.TRENDING, 1): [_repository(FirehoseMode.TRENDING, 2)],
        }
    )
    sleep_calls: list[int] = []

    result = run_firehose_job(
        session=StubSession(),  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=7,
        modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
        sleep_fn=sleep_calls.append,
        per_page=5,
        load_progress=lambda _session: None,
        persist_batch=_persist_batch,
        save_progress=_save_progress,
        today=date(2026, 3, 10),
    )

    assert result.status is FirehoseRunStatus.SUCCESS
    assert [(outcome.mode, outcome.page) for outcome in result.outcomes] == [
        (FirehoseMode.NEW, 1),
        (FirehoseMode.TRENDING, 1),
    ]
    assert [outcome.inserted_count for outcome in result.outcomes] == [1, 1]
    assert provider.calls == [
        (FirehoseMode.NEW, date(2026, 3, 9), 5, 1),
        (FirehoseMode.TRENDING, date(2026, 3, 3), 5, 1),
    ]
    assert sleep_calls == [7]

    progress_snapshot = json.loads((tmp_path / "firehose" / "progress.json").read_text())
    assert progress_snapshot["resume_required"] is False
    assert progress_snapshot["active_mode"] is None
    assert progress_snapshot["anchors"]["new"] is None


def test_firehose_job_fetches_multiple_pages_in_parallel_batches(tmp_path: Path) -> None:
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): [_repository(FirehoseMode.NEW, repository_id) for repository_id in range(1, 6)],
            (FirehoseMode.NEW, 2): [_repository(FirehoseMode.NEW, repository_id) for repository_id in range(6, 11)],
        }
    )

    result = run_firehose_job(
        session=StubSession(),  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=7,
        modes=(FirehoseMode.NEW,),
        sleep_fn=lambda _seconds: None,
        per_page=5,
        pages=2,
        search_lanes=2,
        load_progress=lambda _session: None,
        persist_batch=_persist_batch,
        save_progress=_save_progress,
        today=date(2026, 3, 10),
    )

    assert result.status is FirehoseRunStatus.SUCCESS
    assert [(outcome.mode, outcome.page) for outcome in result.outcomes] == [
        (FirehoseMode.NEW, 1),
        (FirehoseMode.NEW, 2),
    ]
    assert [outcome.inserted_count for outcome in result.outcomes] == [5, 5]
    assert provider.calls == [
        (FirehoseMode.NEW, date(2026, 3, 9), 5, 1),
        (FirehoseMode.NEW, date(2026, 3, 9), 5, 2),
    ]


def test_firehose_job_clears_checkpoint_after_full_cycle_and_starts_fresh(tmp_path: Path) -> None:
    checkpoint_state: dict[str, FirehoseCheckpointState | None] = {"value": None}
    first_provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): [_repository(FirehoseMode.NEW, 1)],
            (FirehoseMode.TRENDING, 1): [_repository(FirehoseMode.TRENDING, 2)],
        }
    )
    second_provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): [_repository(FirehoseMode.NEW, 3)],
        }
    )

    def load_progress(_session: object) -> FirehoseCheckpointState | None:
        return checkpoint_state["value"]

    def save_progress(_session: object, checkpoint: FirehoseCheckpointState) -> None:
        checkpoint_state["value"] = checkpoint

    first_result = run_firehose_job(
        session=StubSession(),  # type: ignore[arg-type]
        provider=first_provider,
        runtime_dir=tmp_path,
        pacing_seconds=1,
        modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
        sleep_fn=lambda _seconds: None,
        per_page=5,
        load_progress=load_progress,
        persist_batch=_persist_batch,
        save_progress=save_progress,
        today=date(2026, 3, 8),
    )

    assert first_result.status is FirehoseRunStatus.SUCCESS
    assert checkpoint_state["value"] is not None
    assert checkpoint_state["value"].resume_required is False
    assert checkpoint_state["value"].active_mode is None
    assert checkpoint_state["value"].new_anchor_date is None
    assert checkpoint_state["value"].trending_anchor_date is None
    assert first_provider.calls == [
        (FirehoseMode.NEW, date(2026, 3, 7), 5, 1),
        (FirehoseMode.TRENDING, date(2026, 3, 1), 5, 1),
    ]

    second_result = run_firehose_job(
        session=StubSession(),  # type: ignore[arg-type]
        provider=second_provider,
        runtime_dir=None,
        pacing_seconds=1,
        modes=(FirehoseMode.NEW,),
        sleep_fn=lambda _seconds: None,
        per_page=5,
        pages=1,
        load_progress=load_progress,
        persist_batch=_persist_batch,
        save_progress=save_progress,
        today=date(2026, 3, 10),
    )

    assert second_result.status is FirehoseRunStatus.SUCCESS
    assert second_provider.calls == [(FirehoseMode.NEW, date(2026, 3, 9), 5, 1)]


def test_firehose_job_stops_after_error_and_rolls_back(tmp_path: Path) -> None:
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): RuntimeError("first page write failed"),
        }
    )
    session = StubSession()

    result = run_firehose_job(
        session=session,  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=1,
        modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
        sleep_fn=lambda _seconds: None,
        per_page=5,
        load_progress=lambda _session: _fresh_checkpoint(),
    )

    assert result.status is FirehoseRunStatus.FAILED
    assert len(result.outcomes) == 1
    assert result.outcomes[0].error == "first page write failed"
    assert session.rollbacks == 1
    assert session.commits == 1


def test_firehose_job_unexpected_runtime_failures_pause_the_agent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): RuntimeError("unexpected firehose crash"),
        }
    )
    session = StubSession()
    emitted_events: list[dict[str, object]] = []
    pause_calls: list[tuple[PauseDecision, int | None]] = []

    def fake_emit_failure_event(_session: object, **kwargs: object) -> int:
        emitted_events.append(kwargs)
        return len(emitted_events)

    monkeypatch.setattr(firehose_job_module, "emit_failure_event", fake_emit_failure_event)
    monkeypatch.setattr(
        firehose_job_module,
        "execute_pause",
        lambda _session, decision, event_id: pause_calls.append((decision, event_id)),
    )

    result = run_firehose_job(
        session=session,  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=1,
        modes=(FirehoseMode.NEW,),
        sleep_fn=lambda _seconds: None,
        per_page=5,
        load_progress=lambda _session: _fresh_checkpoint(),
    )

    assert result.status is FirehoseRunStatus.FAILED
    assert [event["event_type"] for event in emitted_events] == [
        "repository_discovery_failed",
        "agent_paused",
    ]
    assert emitted_events[0]["classification"] is FailureClassification.BLOCKING
    assert pause_calls
    assert pause_calls[0][0].affected_agents == ["firehose"]
    assert pause_calls[0][1] == 1
    assert session.rollbacks == 1
    assert session.commits == 1


def test_firehose_job_timeout_failures_are_retryable_and_do_not_pause(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): TimeoutError("The read operation timed out"),
        }
    )
    session = StubSession()
    emitted_events: list[dict[str, object]] = []
    pause_calls: list[tuple[PauseDecision, int | None]] = []

    def fake_emit_failure_event(_session: object, **kwargs: object) -> int:
        emitted_events.append(kwargs)
        return len(emitted_events)

    monkeypatch.setattr(firehose_job_module, "emit_failure_event", fake_emit_failure_event)
    monkeypatch.setattr(
        firehose_job_module,
        "execute_pause",
        lambda _session, decision, event_id: pause_calls.append((decision, event_id)),
    )

    result = run_firehose_job(
        session=session,  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=1,
        modes=(FirehoseMode.NEW,),
        sleep_fn=lambda _seconds: None,
        per_page=5,
        load_progress=lambda _session: _fresh_checkpoint(),
    )

    assert result.status is FirehoseRunStatus.FAILED
    assert [event["event_type"] for event in emitted_events] == ["repository_discovery_failed"]
    assert emitted_events[0]["classification"] is FailureClassification.RETRYABLE
    assert not pause_calls
    assert session.rollbacks == 1
    assert session.commits == 1


def test_firehose_job_rolls_back_when_pause_emission_fails_for_provider_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): GitHubProviderError("github transport failed"),
        }
    )
    session = StubSession()

    monkeypatch.setattr(
        firehose_job_module,
        "emit_failure_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("event sink failed")),
    )

    result = run_firehose_job(
        session=session,  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=1,
        modes=(FirehoseMode.NEW,),
        sleep_fn=lambda _seconds: None,
        per_page=5,
        load_progress=lambda _session: _fresh_checkpoint(),
    )

    assert result.status is FirehoseRunStatus.FAILED
    assert session.rollbacks == 2
    assert session.commits == 0


def test_firehose_job_returns_skipped_paused_when_agent_is_paused(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(firehose_job_module, "is_agent_paused", lambda *_args, **_kwargs: True)

    result = run_firehose_job(
        session=StubSession(),  # type: ignore[arg-type]
        provider=StubProvider({}),
        runtime_dir=tmp_path,
        pacing_seconds=1,
        sleep_fn=lambda _seconds: None,
    )

    assert result.status is FirehoseRunStatus.SKIPPED_PAUSED
    assert result.outcomes == []


def test_firehose_job_sleeps_for_rate_limit_backoff_before_stopping(tmp_path: Path) -> None:
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): GitHubRateLimitError(status_code=429, retry_after_seconds=120),
        }
    )
    session = StubSession()
    sleep_calls: list[int] = []

    result = run_firehose_job(
        session=session,  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=5,
        modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
        per_page=5,
        load_progress=lambda _session: _fresh_checkpoint(),
    )

    assert result.status is FirehoseRunStatus.FAILED
    assert len(result.outcomes) == 1
    assert result.outcomes[0].error == "GitHub rate limit exceeded with status 429; retry after 120s"
    assert sleep_calls == [120]
    assert session.rollbacks == 1
    assert session.commits == 1


def test_firehose_job_resumes_from_stored_mode_page_and_anchor(tmp_path: Path) -> None:
    provider = StubProvider(
        {
            (FirehoseMode.TRENDING, 3): [_repository(FirehoseMode.TRENDING, 30)],
        }
    )
    checkpoint = FirehoseCheckpointState(
        source_provider="github",
        active_mode=FirehoseMode.TRENDING,
        next_page=3,
        new_anchor_date=date(2026, 3, 5),
        trending_anchor_date=date(2026, 2, 28),
        run_started_at=datetime(2026, 3, 7, 10, 0, tzinfo=timezone.utc),
        resume_required=True,
        last_checkpointed_at=datetime(2026, 3, 7, 10, 5, tzinfo=timezone.utc),
        pages_processed_in_run=2,
    )

    result = run_firehose_job(
        session=StubSession(),  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=None,
        pacing_seconds=1,
        modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
        sleep_fn=lambda _seconds: None,
        per_page=10,
        pages=3,
        load_progress=lambda _session: checkpoint,
        persist_batch=_persist_batch,
        save_progress=_save_progress,
    )

    assert result.status is FirehoseRunStatus.SUCCESS
    assert provider.calls == [(FirehoseMode.TRENDING, date(2026, 2, 28), 10, 3)]
    assert result.outcomes[0].page == 3
    assert result.outcomes[0].anchor_date == date(2026, 2, 28)


def test_firehose_job_clears_checkpoint_after_full_page_budget_for_last_mode(
    tmp_path: Path,
) -> None:
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): [_repository(FirehoseMode.NEW, 100 + idx) for idx in range(2)],
        }
    )
    saved_checkpoints: list[FirehoseCheckpointState] = []

    result = run_firehose_job(
        session=StubSession(),  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=None,
        pacing_seconds=1,
        modes=(FirehoseMode.NEW,),
        sleep_fn=lambda _seconds: None,
        per_page=2,
        pages=1,
        load_progress=lambda _session: _fresh_checkpoint(),
        save_progress=lambda _session, checkpoint: saved_checkpoints.append(checkpoint),
        persist_batch=_persist_batch,
    )

    assert result.status is FirehoseRunStatus.SUCCESS
    assert saved_checkpoints[0].active_mode is None
    assert saved_checkpoints[0].next_page == 1
    assert saved_checkpoints[0].resume_required is False
    assert saved_checkpoints[0].pages_processed_in_run == 0


def test_firehose_job_stops_between_pages_when_shutdown_requested() -> None:
    stop_flag = [False]
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): [_repository(FirehoseMode.NEW, 1)],
            (FirehoseMode.NEW, 2): [_repository(FirehoseMode.NEW, 2)],
        }
    )
    sleep_calls: list[int] = []

    def interruptible_sleep(seconds: int) -> None:
        sleep_calls.append(seconds)
        stop_flag[0] = True

    result = run_firehose_job(
        session=StubSession(),  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=None,
        pacing_seconds=5,
        modes=(FirehoseMode.NEW,),
        per_page=1,
        pages=2,
        sleep_fn=interruptible_sleep,
        should_stop=lambda: stop_flag[0],
        load_progress=lambda _session: _fresh_checkpoint(),
        persist_batch=_persist_batch,
        save_progress=_save_progress,
    )

    assert provider.calls == [(FirehoseMode.NEW, date(2026, 3, 7), 1, 1)]
    assert sleep_calls == [5]
    assert len(result.outcomes) == 1
    assert result.outcomes[0].page == 1


def test_firehose_job_returns_partial_failure_when_one_mode_succeeds_and_one_fails(
    tmp_path: Path,
) -> None:
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): [],
            (FirehoseMode.TRENDING, 1): RuntimeError("boom"),
        }
    )

    result = run_firehose_job(
        session=StubSession(),  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=0,
        modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
        sleep_fn=lambda _seconds: None,
        load_progress=lambda _session: _fresh_checkpoint(),
        persist_batch=_persist_batch,
        save_progress=_save_progress,
    )

    assert result.status is FirehoseRunStatus.PARTIAL_FAILURE
    assert result.outcomes[0].error is None
    assert result.outcomes[0].fetched_count == 0
    assert result.outcomes[1].error == "boom"


def test_firehose_job_rolls_back_queue_rows_when_checkpoint_save_fails(tmp_path: Path) -> None:
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): [_repository(FirehoseMode.NEW, 1)],
        }
    )
    engine = create_engine(f"sqlite:///{tmp_path / 'checkpoint-failure.db'}")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)

    def failing_save_progress(_session: Session, _checkpoint: FirehoseCheckpointState) -> None:
        raise RuntimeError("checkpoint write failed")

    try:
        result = run_firehose_job(
            session=session,
            provider=provider,
            runtime_dir=tmp_path,
            pacing_seconds=1,
            modes=(FirehoseMode.NEW,),
            sleep_fn=lambda _seconds: None,
            load_progress=lambda _session: _fresh_checkpoint(),
            save_progress=failing_save_progress,
        )
        persisted_rows = session.exec(select(RepositoryIntake)).all()
    finally:
        session.close()

    assert result.status is FirehoseRunStatus.FAILED
    assert result.outcomes[0].fetched_count == 1
    assert result.outcomes[0].error == "checkpoint write failed"
    assert persisted_rows == []


def test_firehose_job_advances_to_next_mode_after_hitting_page_budget(tmp_path: Path) -> None:
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): [_repository(FirehoseMode.NEW, 1)],
            (FirehoseMode.NEW, 2): [_repository(FirehoseMode.NEW, 2)],
            (FirehoseMode.TRENDING, 1): [],
        }
    )

    result = run_firehose_job(
        session=StubSession(),  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=None,
        pacing_seconds=0,
        modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
        per_page=1,
        pages=2,
        sleep_fn=lambda _seconds: None,
        load_progress=lambda _session: _fresh_checkpoint(),
        persist_batch=_persist_batch,
        save_progress=_save_progress,
    )

    assert result.status is FirehoseRunStatus.SUCCESS
    assert [(outcome.mode, outcome.page) for outcome in result.outcomes] == [
        (FirehoseMode.NEW, 1),
        (FirehoseMode.NEW, 2),
        (FirehoseMode.TRENDING, 1),
    ]
    assert provider.calls == [
        (FirehoseMode.NEW, date(2026, 3, 7), 1, 1),
        (FirehoseMode.NEW, date(2026, 3, 7), 1, 2),
        (FirehoseMode.TRENDING, date(2026, 3, 1), 1, 1),
    ]


def test_firehose_job_initializes_checkpoint_from_requested_trending_mode(
    tmp_path: Path,
) -> None:
    provider = StubProvider(
        {
            (FirehoseMode.TRENDING, 1): [],
        }
    )

    result = run_firehose_job(
        session=StubSession(),  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=0,
        modes=(FirehoseMode.TRENDING,),
        per_page=5,
        sleep_fn=lambda _seconds: None,
        load_progress=lambda _session: None,
        persist_batch=_persist_batch,
        save_progress=_save_progress,
        today=date(2026, 3, 8),
    )

    assert result.status is FirehoseRunStatus.SUCCESS
    assert provider.calls == [(FirehoseMode.TRENDING, date(2026, 3, 1), 5, 1)]


def test_firehose_job_respects_page_budget_on_resume(tmp_path: Path) -> None:
    """A resumed Firehose run must not overshoot the per-mode page budget.

    If pages=2 and the checkpoint says next_page=2 (page 1 was consumed before
    interruption), the resumed invocation should only process 1 more page for that
    mode — not a fresh budget of 2.
    """
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 2): [_repository(FirehoseMode.NEW, 20)],
            (FirehoseMode.NEW, 3): [_repository(FirehoseMode.NEW, 30)],
            (FirehoseMode.TRENDING, 1): [],
        }
    )
    resumed_checkpoint = FirehoseCheckpointState(
        source_provider="github",
        active_mode=FirehoseMode.NEW,
        next_page=2,
        new_anchor_date=date(2026, 3, 7),
        trending_anchor_date=date(2026, 3, 1),
        run_started_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
        resume_required=True,
        last_checkpointed_at=datetime(2026, 3, 8, 12, 5, tzinfo=timezone.utc),
        pages_processed_in_run=1,
    )

    result = run_firehose_job(
        session=StubSession(),  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=None,
        pacing_seconds=0,
        modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
        per_page=1,
        pages=2,
        sleep_fn=lambda _seconds: None,
        load_progress=lambda _session: resumed_checkpoint,
        persist_batch=_persist_batch,
        save_progress=_save_progress,
    )

    assert result.status is FirehoseRunStatus.SUCCESS
    # Should process page 2 of NEW (1 remaining in budget), then move to TRENDING.
    # Should NOT process page 3 of NEW — that would overshoot the budget.
    assert [(outcome.mode, outcome.page) for outcome in result.outcomes] == [
        (FirehoseMode.NEW, 2),
        (FirehoseMode.TRENDING, 1),
    ]
    assert provider.calls == [
        (FirehoseMode.NEW, date(2026, 3, 7), 1, 2),
        (FirehoseMode.TRENDING, date(2026, 3, 1), 1, 1),
    ]


def test_firehose_job_surfaces_artifact_write_failures_as_structured_results(tmp_path: Path) -> None:
    provider = StubProvider({(FirehoseMode.NEW, 1): [_repository(FirehoseMode.NEW, 1)]})

    def write_artifact(
        *,
        runtime_dir: Path | None,
        status: FirehoseRunStatus,
        outcomes: list[object],
        checkpoint: FirehoseCheckpointState,
    ) -> Path | None:
        del runtime_dir, status, outcomes, checkpoint
        raise OSError("runtime directory is read-only")

    result = run_firehose_job(
        session=StubSession(),  # type: ignore[arg-type]
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=1,
        modes=(FirehoseMode.NEW,),
        sleep_fn=lambda _seconds: None,
        write_artifact=write_artifact,
        load_progress=lambda _session: _fresh_checkpoint(),
        persist_batch=_persist_batch,
        save_progress=_save_progress,
    )

    assert isinstance(result, FirehoseRunResult)
    assert result.status is FirehoseRunStatus.PARTIAL_FAILURE
    assert result.artifact_path is None
    assert result.artifact_error == "runtime directory is read-only"

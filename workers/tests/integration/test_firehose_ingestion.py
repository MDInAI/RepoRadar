from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine, select

import agentic_workers.storage.firehose_progress as firehose_progress_module
from agentic_workers.jobs.firehose_job import FirehoseRunStatus, run_firehose_job
from agentic_workers.providers.github_provider import DiscoveredRepository, FirehoseMode
from agentic_workers.storage.backend_models import (
    FirehoseProgress,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryQueueStatus,
    SQLModel,
)
from agentic_workers.storage.firehose_progress import (
    FirehoseCheckpointState,
    save_firehose_progress,
)


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


def _repository(mode: FirehoseMode, repository_id: int) -> DiscoveredRepository:
    return DiscoveredRepository(
        github_repository_id=repository_id,
        owner_login="octocat",
        repository_name=f"repo-{repository_id}",
        full_name=f"octocat/repo-{repository_id}",
        created_at=datetime(2026, 3, 7, repository_id % 24, 0, tzinfo=timezone.utc),
        firehose_discovery_mode=mode,
    )


def _make_session(tmp_path: Path) -> Session:
    database_url = f"sqlite:///{tmp_path / 'firehose.db'}"
    engine = create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_firehose_job_persists_resume_checkpoint_and_runtime_snapshot(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): [_repository(FirehoseMode.NEW, 101)],
            (FirehoseMode.TRENDING, 1): [_repository(FirehoseMode.TRENDING, 202)],
        }
    )

    with _make_session(tmp_path) as session:
        result = run_firehose_job(
            session=session,
            provider=provider,
            runtime_dir=runtime_dir,
            pacing_seconds=1,
            modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
            per_page=5,
            sleep_fn=lambda _seconds: None,
            today=date(2026, 3, 8),
        )
        rows = session.exec(
            select(RepositoryIntake).order_by(RepositoryIntake.github_repository_id)
        ).all()
        checkpoint = session.get(FirehoseProgress, "github")

    assert result.status is FirehoseRunStatus.SUCCESS
    assert [row.github_repository_id for row in rows] == [101, 202]
    assert rows[0].discovery_source is RepositoryDiscoverySource.FIREHOSE
    assert rows[0].queue_status is RepositoryQueueStatus.PENDING
    assert rows[0].firehose_discovery_mode is RepositoryFirehoseMode.NEW
    assert checkpoint is not None
    assert checkpoint.resume_required is False
    assert checkpoint.active_mode is None
    assert checkpoint.next_page == 1
    assert checkpoint.pages_processed_in_run == 0

    progress_snapshot = json.loads((runtime_dir / "firehose" / "progress.json").read_text())
    assert progress_snapshot["resume_required"] is False
    assert progress_snapshot["active_mode"] is None
    assert progress_snapshot["pages_processed_in_run"] == 0

    artifact = json.loads(result.artifact_path.read_text())  # type: ignore[union-attr]
    assert artifact["checkpoint"]["resume_required"] is False
    assert [outcome["mode"] for outcome in artifact["outcomes"]] == ["new", "trending"]


def test_firehose_job_resumes_saved_mode_page_with_frozen_anchor_after_interruption(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime"
    first_provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): [_repository(FirehoseMode.NEW, 101)],
        }
    )
    second_provider = StubProvider(
        {
            (FirehoseMode.TRENDING, 1): [_repository(FirehoseMode.TRENDING, 202)],
        }
    )
    stop_flag = [False]

    def interruptible_sleep(_seconds: int) -> None:
        stop_flag[0] = True

    with _make_session(tmp_path) as session:
        first_result = run_firehose_job(
            session=session,
            provider=first_provider,
            runtime_dir=runtime_dir,
            pacing_seconds=1,
            modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
            per_page=5,
            sleep_fn=interruptible_sleep,
            should_stop=lambda: stop_flag[0],
            today=date(2026, 3, 8),
        )
        checkpoint_after_first_run = session.get(FirehoseProgress, "github")
        assert checkpoint_after_first_run is not None
        resume_required = checkpoint_after_first_run.resume_required
        active_mode = checkpoint_after_first_run.active_mode.value
        trending_anchor_date = checkpoint_after_first_run.trending_anchor_date
        second_result = run_firehose_job(
            session=session,
            provider=second_provider,
            runtime_dir=runtime_dir,
            pacing_seconds=1,
            modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
            per_page=5,
            sleep_fn=lambda _seconds: None,
            today=date(2026, 3, 20),
        )

    assert first_result.status is FirehoseRunStatus.SUCCESS
    assert resume_required is True
    assert active_mode == "trending"
    assert trending_anchor_date == date(2026, 3, 1)
    assert first_provider.calls == [(FirehoseMode.NEW, date(2026, 3, 7), 5, 1)]

    assert second_result.status is FirehoseRunStatus.SUCCESS
    assert second_provider.calls == [(FirehoseMode.TRENDING, date(2026, 3, 1), 5, 1)]


def test_firehose_progress_initialize_computes_anchors_from_today() -> None:
    from agentic_workers.storage.firehose_progress import initialize_firehose_progress
    from agentic_workers.providers.github_provider import FirehoseMode
    
    today = date(2026, 3, 10)
    checkpoint = initialize_firehose_progress(today=today)
    
    assert checkpoint.active_mode == FirehoseMode.NEW
    assert checkpoint.new_anchor_date == date(2026, 3, 9)  # today - 1
    assert checkpoint.trending_anchor_date == date(2026, 3, 3)  # today - 7
    assert checkpoint.resume_required is True

def test_firehose_progress_initialize_computes_anchors_from_started_at_if_no_today() -> None:
    from agentic_workers.storage.firehose_progress import initialize_firehose_progress
    from agentic_workers.providers.github_provider import FirehoseMode
    
    started_at = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    checkpoint = initialize_firehose_progress(started_at=started_at)
    
    assert checkpoint.active_mode == FirehoseMode.NEW
    assert checkpoint.new_anchor_date == date(2026, 3, 9)  # today - 1
    assert checkpoint.trending_anchor_date == date(2026, 3, 3)  # today - 7
    assert checkpoint.resume_required is True

def test_firehose_job_retries_same_page_after_checkpoint_failure_without_duplicate_rows(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime"
    provider = StubProvider(
        {
            (FirehoseMode.NEW, 1): [_repository(FirehoseMode.NEW, 999)],
        }
    )

    with _make_session(tmp_path) as session:
        first_result = run_firehose_job(
            session=session,
            provider=provider,
            runtime_dir=runtime_dir,
            pacing_seconds=1,
            modes=(FirehoseMode.NEW,),
            per_page=5,
            sleep_fn=lambda _seconds: None,
            today=date(2026, 3, 8),
            save_progress=lambda _session, _checkpoint: (_ for _ in ()).throw(
                RuntimeError("checkpoint write failed")
            ),
        )
        rows_after_failure = session.exec(select(RepositoryIntake)).all()
        second_result = run_firehose_job(
            session=session,
            provider=provider,
            runtime_dir=runtime_dir,
            pacing_seconds=1,
            modes=(FirehoseMode.NEW,),
            per_page=5,
            sleep_fn=lambda _seconds: None,
            today=date(2026, 3, 8),
        )
        rows_after_retry = session.exec(select(RepositoryIntake)).all()

    assert first_result.status is FirehoseRunStatus.FAILED
    assert first_result.outcomes[0].error == "checkpoint write failed"
    assert len(rows_after_failure) == 0

    assert second_result.status is FirehoseRunStatus.SUCCESS
    assert second_result.outcomes[0].inserted_count == 1
    assert second_result.outcomes[0].skipped_count == 0
    assert len(rows_after_retry) == 1


def test_firehose_progress_save_updates_existing_row_without_duplicates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_updated_at = datetime(2026, 3, 8, 9, 0, tzinfo=timezone.utc)
    second_updated_at = datetime(2026, 3, 8, 9, 5, tzinfo=timezone.utc)
    updated_at_values = iter([first_updated_at, second_updated_at])

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:
            value = next(updated_at_values)
            if tz is None:
                return value.replace(tzinfo=None)
            return value.astimezone(tz)

    monkeypatch.setattr(firehose_progress_module, "datetime", FrozenDateTime)

    checkpoint_a = FirehoseCheckpointState(
        source_provider="github",
        active_mode=FirehoseMode.NEW,
        next_page=2,
        new_anchor_date=date(2026, 3, 7),
        trending_anchor_date=date(2026, 3, 1),
        run_started_at=datetime(2026, 3, 8, 8, 0, tzinfo=timezone.utc),
        resume_required=True,
        last_checkpointed_at=first_updated_at,
    )
    checkpoint_b = FirehoseCheckpointState(
        source_provider="github",
        active_mode=FirehoseMode.TRENDING,
        next_page=4,
        new_anchor_date=date(2026, 3, 7),
        trending_anchor_date=date(2026, 3, 1),
        run_started_at=datetime(2026, 3, 8, 8, 30, tzinfo=timezone.utc),
        resume_required=True,
        last_checkpointed_at=second_updated_at,
        pages_processed_in_run=3,
    )

    with _make_session(tmp_path) as session:
        save_firehose_progress(session, checkpoint_a)
        first_row = session.get(FirehoseProgress, "github")
        assert first_row is not None
        assert first_row.updated_at == first_updated_at

        save_firehose_progress(session, checkpoint_b)
        rows = session.exec(select(FirehoseProgress)).all()

    assert len(rows) == 1
    assert rows[0].active_mode is RepositoryFirehoseMode.TRENDING
    assert rows[0].next_page == 4
    assert rows[0].pages_processed_in_run == 3
    assert rows[0].run_started_at == datetime(2026, 3, 8, 8, 30, tzinfo=timezone.utc)
    assert rows[0].last_checkpointed_at == second_updated_at
    assert rows[0].updated_at == second_updated_at
    assert rows[0].updated_at > first_updated_at

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, create_engine

from agentic_workers.jobs.firehose_job import (
    FirehoseMode,
    FirehoseRunResult,
    FirehoseRunStatus,
    run_firehose_job,
)
from agentic_workers.providers.github_provider import DiscoveredRepository
from agentic_workers.storage.repository_intake import IntakePersistenceResult


class StubProvider:
    def __init__(self, responses: dict[FirehoseMode, list[DiscoveredRepository]]) -> None:
        self.responses = responses
        self.calls: list[tuple[FirehoseMode, int, int]] = []

    def discover(self, *, mode: FirehoseMode, per_page: int = 25, page: int = 1) -> list[DiscoveredRepository]:
        self.calls.append((mode, per_page, page))
        return list(self.responses[mode])


def _repository(mode: FirehoseMode, repository_id: int) -> DiscoveredRepository:
    return DiscoveredRepository(
        github_repository_id=repository_id,
        owner_login="octocat",
        repository_name=f"repo-{repository_id}",
        full_name=f"octocat/repo-{repository_id}",
        firehose_discovery_mode=mode,
    )


def test_firehose_job_sleeps_between_modes_and_collects_success_results(tmp_path: Path) -> None:
    provider = StubProvider(
        {
            FirehoseMode.NEW: [_repository(FirehoseMode.NEW, 1)],
            FirehoseMode.TRENDING: [_repository(FirehoseMode.TRENDING, 2)],
        }
    )
    persisted_batches: list[tuple[FirehoseMode, list[DiscoveredRepository]]] = []
    sleep_calls: list[int] = []

    def persist_batch(
        _session: object,
        repositories: list[DiscoveredRepository],
        *,
        mode: FirehoseMode,
    ) -> IntakePersistenceResult:
        persisted_batches.append((mode, repositories))
        return IntakePersistenceResult(inserted_count=len(repositories), skipped_count=0)

    result = run_firehose_job(
        session=object(),
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=7,
        modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
        sleep_fn=sleep_calls.append,
        persist_batch=persist_batch,
    )

    assert result.status is FirehoseRunStatus.SUCCESS
    assert [outcome.mode for outcome in result.outcomes] == [FirehoseMode.NEW, FirehoseMode.TRENDING]
    assert [outcome.inserted_count for outcome in result.outcomes] == [1, 1]
    assert persisted_batches == [
        (FirehoseMode.NEW, [_repository(FirehoseMode.NEW, 1)]),
        (FirehoseMode.TRENDING, [_repository(FirehoseMode.TRENDING, 2)]),
    ]
    assert sleep_calls == [7]


def test_firehose_job_rolls_back_session_after_persistence_failure(tmp_path: Path) -> None:
    provider = StubProvider(
        {
            FirehoseMode.NEW: [_repository(FirehoseMode.NEW, 1)],
            FirehoseMode.TRENDING: [_repository(FirehoseMode.TRENDING, 2)],
        }
    )
    engine = create_engine(f"sqlite:///{tmp_path / 'rollback.db'}")
    session = Session(engine)
    persisted_modes: list[FirehoseMode] = []

    def persist_batch(
        session: Session,
        repositories: list[DiscoveredRepository],
        *,
        mode: FirehoseMode,
    ) -> IntakePersistenceResult:
        if mode is FirehoseMode.NEW:
            session.begin()
            raise RuntimeError("first batch write failed")
        persisted_modes.append(mode)
        return IntakePersistenceResult(inserted_count=len(repositories), skipped_count=0)

    try:
        result = run_firehose_job(
            session=session,
            provider=provider,
            runtime_dir=tmp_path,
            pacing_seconds=1,
            modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
            sleep_fn=lambda _seconds: None,
            persist_batch=persist_batch,
        )
    finally:
        session.close()

    assert result.status is FirehoseRunStatus.PARTIAL_FAILURE
    assert persisted_modes == [FirehoseMode.TRENDING]
    assert result.outcomes[0].error == "first batch write failed"
    assert result.outcomes[1].inserted_count == 1


def test_firehose_job_stops_at_mode_boundary_when_shutdown_requested() -> None:
    """After pacing sleep returns early (SIGINT), should_stop prevents the next mode from running."""
    stop_flag = [False]
    discover_modes: list[FirehoseMode] = []

    class TrackingProvider:
        def discover(
            self,
            *,
            mode: FirehoseMode,
            per_page: int = 100,
            page: int = 1,
        ) -> list[DiscoveredRepository]:
            discover_modes.append(mode)
            return [_repository(mode, 1)]

    def interruptible_sleep(seconds: int) -> None:
        stop_flag[0] = True  # simulates SIGINT waking up the pacing sleep early

    result = run_firehose_job(
        session=object(),
        provider=TrackingProvider(),
        runtime_dir=None,
        pacing_seconds=1,
        modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
        sleep_fn=interruptible_sleep,
        should_stop=lambda: stop_flag[0],
        persist_batch=lambda _s, repos, mode: IntakePersistenceResult(
            inserted_count=len(repos), skipped_count=0
        ),
    )

    assert discover_modes == [FirehoseMode.NEW]  # TRENDING skipped after sleep set stop_flag
    assert len(result.outcomes) == 1
    assert result.outcomes[0].mode is FirehoseMode.NEW
    assert result.status is FirehoseRunStatus.SUCCESS


def test_firehose_job_fetches_multiple_pages_per_mode(tmp_path: Path) -> None:
    """When pages > 1, the job issues successive discover() calls until a partial page."""
    discover_calls: list[tuple[FirehoseMode, int]] = []

    class MultiPageProvider:
        def discover(
            self,
            *,
            mode: FirehoseMode,
            per_page: int = 100,
            page: int = 1,
        ) -> list[DiscoveredRepository]:
            discover_calls.append((mode, page))
            if page == 1:
                return [_repository(mode, page * 100 + i) for i in range(per_page)]
            return []  # page 2 is empty — signals end of results

    result = run_firehose_job(
        session=object(),
        provider=MultiPageProvider(),
        runtime_dir=None,
        pacing_seconds=0,
        modes=(FirehoseMode.NEW,),
        pages=2,
        sleep_fn=lambda _seconds: None,
        persist_batch=lambda _s, repos, mode: IntakePersistenceResult(
            inserted_count=len(repos), skipped_count=0
        ),
    )

    assert discover_calls == [(FirehoseMode.NEW, 1), (FirehoseMode.NEW, 2)]
    # fetched_count is the total across all pages (100 from page 1, 0 from page 2)
    assert result.outcomes[0].fetched_count == 100
    assert result.outcomes[0].inserted_count == 100


def test_firehose_job_stops_paging_on_partial_page(tmp_path: Path) -> None:
    """A page with fewer results than per_page signals the end — no further requests are made."""
    discover_calls: list[tuple[FirehoseMode, int]] = []

    class ShortFirstPageProvider:
        def discover(
            self,
            *,
            mode: FirehoseMode,
            per_page: int = 100,
            page: int = 1,
        ) -> list[DiscoveredRepository]:
            discover_calls.append((mode, page))
            return [_repository(mode, i) for i in range(5)]  # always fewer than per_page

    run_firehose_job(
        session=object(),
        provider=ShortFirstPageProvider(),
        runtime_dir=None,
        pacing_seconds=0,
        modes=(FirehoseMode.NEW,),
        pages=3,  # would fetch 3 pages if not stopped early
        sleep_fn=lambda _seconds: None,
        persist_batch=lambda _s, repos, mode: IntakePersistenceResult(
            inserted_count=len(repos), skipped_count=0
        ),
    )

    assert discover_calls == [(FirehoseMode.NEW, 1)]  # stopped after partial page 1


def test_firehose_job_classifies_empty_batch_alongside_error_as_partial_failure(tmp_path: Path) -> None:
    """A zero-result batch (no error) alongside an errored batch must yield PARTIAL_FAILURE, not FAILED."""

    class EmptyThenErrorProvider:
        def discover(
            self,
            *,
            mode: FirehoseMode,
            per_page: int = 25,
            page: int = 1,
        ) -> list[DiscoveredRepository]:
            if mode is FirehoseMode.NEW:
                return []
            raise RuntimeError("boom")

    result = run_firehose_job(
        session=object(),
        provider=EmptyThenErrorProvider(),
        runtime_dir=tmp_path,
        pacing_seconds=0,
        modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
        sleep_fn=lambda _seconds: None,
        persist_batch=lambda _session, repositories, mode: IntakePersistenceResult(
            inserted_count=0, skipped_count=0
        ),
    )

    assert result.status is FirehoseRunStatus.PARTIAL_FAILURE
    assert result.outcomes[0].error is None
    assert result.outcomes[0].fetched_count == 0
    assert result.outcomes[1].error == "boom"


def test_firehose_job_records_accurate_fetched_count_when_persistence_fails(tmp_path: Path) -> None:
    """fetched_count must reflect actual discovered repos even when persist raises."""
    discovered = [_repository(FirehoseMode.NEW, i) for i in range(5)]
    provider = StubProvider({FirehoseMode.NEW: discovered})

    def failing_persist(
        _session: object,
        repositories: list[DiscoveredRepository],
        *,
        mode: FirehoseMode,
    ) -> IntakePersistenceResult:
        raise RuntimeError("write failed after discover succeeded")

    result = run_firehose_job(
        session=object(),
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=1,
        modes=(FirehoseMode.NEW,),
        sleep_fn=lambda _seconds: None,
        persist_batch=failing_persist,
    )

    assert result.status is FirehoseRunStatus.FAILED
    assert result.outcomes[0].fetched_count == 5
    assert result.outcomes[0].inserted_count == 0
    assert result.outcomes[0].error == "write failed after discover succeeded"


def test_firehose_job_surfaces_artifact_write_failures_as_structured_results(tmp_path: Path) -> None:
    provider = StubProvider({FirehoseMode.NEW: [_repository(FirehoseMode.NEW, 1)]})

    def write_artifact(
        *,
        runtime_dir: Path | None,
        status: FirehoseRunStatus,
        outcomes: list[object],
    ) -> Path | None:
        raise OSError("runtime directory is read-only")

    result = run_firehose_job(
        session=object(),
        provider=provider,
        runtime_dir=tmp_path,
        pacing_seconds=1,
        modes=(FirehoseMode.NEW,),
        sleep_fn=lambda _seconds: None,
        persist_batch=lambda _session, repositories, mode: IntakePersistenceResult(
            inserted_count=len(repositories),
            skipped_count=0,
        ),
        write_artifact=write_artifact,
    )

    assert isinstance(result, FirehoseRunResult)
    assert result.status is FirehoseRunStatus.PARTIAL_FAILURE
    assert result.artifact_path is None
    assert result.artifact_error == "runtime directory is read-only"

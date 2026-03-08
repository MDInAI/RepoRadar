from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, create_engine, select

from agentic_workers.jobs.firehose_job import FirehoseMode, FirehoseRunStatus, run_firehose_job
from agentic_workers.providers.github_provider import DiscoveredRepository
from agentic_workers.storage.backend_models import (
    RepositoryDiscoverySource,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryFirehoseMode,
    SQLModel,
)


class StubProvider:
    def __init__(self, responses: dict[FirehoseMode, list[DiscoveredRepository] | Exception]) -> None:
        self.responses = responses

    def discover(self, *, mode: FirehoseMode, per_page: int = 25, page: int = 1) -> list[DiscoveredRepository]:
        response = self.responses[mode]
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


def test_firehose_job_persists_rows_and_skips_duplicate_discoveries(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    provider = StubProvider({FirehoseMode.NEW: [_repository(FirehoseMode.NEW, 101)]})

    with _make_session(tmp_path) as session:
        first_result = run_firehose_job(
            session=session,
            provider=provider,
            runtime_dir=runtime_dir,
            pacing_seconds=1,
            modes=(FirehoseMode.NEW,),
            sleep_fn=lambda _seconds: None,
        )
        second_result = run_firehose_job(
            session=session,
            provider=provider,
            runtime_dir=runtime_dir,
            pacing_seconds=1,
            modes=(FirehoseMode.NEW,),
            sleep_fn=lambda _seconds: None,
        )

        rows = session.exec(select(RepositoryIntake)).all()

    assert first_result.status is FirehoseRunStatus.SUCCESS
    assert first_result.outcomes[0].inserted_count == 1
    assert second_result.status is FirehoseRunStatus.SUCCESS
    assert second_result.outcomes[0].skipped_count == 1
    assert len(rows) == 1
    assert rows[0].discovery_source is RepositoryDiscoverySource.FIREHOSE
    assert rows[0].queue_status is RepositoryQueueStatus.PENDING
    assert rows[0].firehose_discovery_mode is RepositoryFirehoseMode.NEW


def test_firehose_job_records_failures_without_removing_existing_rows(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    provider = StubProvider(
        {
            FirehoseMode.NEW: [_repository(FirehoseMode.NEW, 101)],
            FirehoseMode.TRENDING: RuntimeError("github search rate limited"),
        }
    )

    with _make_session(tmp_path) as session:
        result = run_firehose_job(
            session=session,
            provider=provider,
            runtime_dir=runtime_dir,
            pacing_seconds=1,
            modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
            sleep_fn=lambda _seconds: None,
        )
        rows = session.exec(select(RepositoryIntake)).all()

    assert result.status is FirehoseRunStatus.PARTIAL_FAILURE
    assert len(rows) == 1
    assert result.artifact_path is not None
    artifact = json.loads(result.artifact_path.read_text())
    assert artifact["status"] == "partial_failure"
    assert artifact["outcomes"][1]["error"] == "github search rate limited"

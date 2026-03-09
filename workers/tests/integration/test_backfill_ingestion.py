from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from sqlmodel import Session, create_engine, select

from agentic_workers.jobs.backfill_job import BackfillRunStatus, run_backfill_job
from agentic_workers.providers.github_provider import DiscoveredRepository, FirehoseMode
from agentic_workers.storage.backend_models import (
    BackfillProgress,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryQueueStatus,
    SQLModel,
)
from agentic_workers.storage.repository_intake import persist_firehose_batch


class RecordingProvider:
    def __init__(
        self,
        responses: dict[tuple[date, date, str | None, int], list[DiscoveredRepository]],
    ) -> None:
        self.responses = responses
        self.calls: list[tuple[date, date, str | None, int]] = []

    def discover_backfill(
        self,
        *,
        window_start_date: date,
        created_before_boundary: date,
        created_before_cursor: datetime | None = None,
        per_page: int = 25,
        page: int = 1,
    ) -> list[DiscoveredRepository]:
        key = (
            window_start_date,
            created_before_boundary,
            created_before_cursor.isoformat() if created_before_cursor is not None else None,
            page,
        )
        self.calls.append(key)
        return list(self.responses.get(key, []))


def _repository(repository_id: int) -> DiscoveredRepository:
    return DiscoveredRepository(
        github_repository_id=repository_id,
        owner_login="octocat",
        repository_name=f"repo-{repository_id}",
        full_name=f"octocat/repo-{repository_id}",
        created_at=datetime(2026, 2, 28, repository_id % 24, 0, tzinfo=timezone.utc),
    )


def _make_session(tmp_path: Path) -> Session:
    database_url = f"sqlite:///{tmp_path / 'backfill.db'}"
    engine = create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_backfill_job_resumes_from_stored_checkpoint_and_writes_artifacts(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    provider = RecordingProvider(
        {
            (date(2026, 2, 6), date(2026, 3, 8), None, 1): [_repository(101), _repository(102)],
            (
                date(2026, 2, 6),
                date(2026, 3, 8),
                "2026-02-28T05:00:00+00:00",
                1,
            ): [_repository(103)],
        }
    )

    with _make_session(tmp_path) as session:
        first_result = run_backfill_job(
            session=session,
            provider=provider,
            runtime_dir=runtime_dir,
            pacing_seconds=1,
            per_page=2,
            pages=1,
            window_days=30,
            min_created_date=date(2008, 1, 1),
            sleep_fn=lambda _seconds: None,
            today=date(2026, 3, 8),
        )
        second_result = run_backfill_job(
            session=session,
            provider=provider,
            runtime_dir=runtime_dir,
            pacing_seconds=1,
            per_page=2,
            pages=1,
            window_days=30,
            min_created_date=date(2008, 1, 1),
            sleep_fn=lambda _seconds: None,
            today=date(2026, 3, 8),
        )

        rows = session.exec(
            select(RepositoryIntake).order_by(RepositoryIntake.github_repository_id)
        ).all()
        checkpoint = session.get(BackfillProgress, "github")

    assert provider.calls == [
        (date(2026, 2, 6), date(2026, 3, 8), None, 1),
        (date(2026, 2, 6), date(2026, 3, 8), "2026-02-28T05:00:00+00:00", 1),
    ]
    assert first_result.status is BackfillRunStatus.SUCCESS
    assert first_result.outcomes[0].inserted_count == 2
    assert second_result.status is BackfillRunStatus.SUCCESS
    assert second_result.outcomes[0].inserted_count == 1
    assert [row.github_repository_id for row in rows] == [101, 102, 103]
    assert all(row.discovery_source is RepositoryDiscoverySource.BACKFILL for row in rows)
    assert all(row.firehose_discovery_mode is None for row in rows)
    assert checkpoint is not None
    assert checkpoint.created_before_boundary == date(2026, 2, 6)
    assert checkpoint.created_before_cursor is None
    assert checkpoint.next_page == 1
    assert checkpoint.pages_processed_in_run == 0
    assert checkpoint.exhausted is False
    assert second_result.artifact_path is not None

    progress_snapshot = json.loads((runtime_dir / "backfill" / "progress.json").read_text())
    assert progress_snapshot["resume_required"] is False

    artifact = json.loads(second_result.artifact_path.read_text())
    assert artifact["status"] == "success"
    assert artifact["checkpoint"]["created_before_boundary"] == "2026-02-06"
    assert artifact["checkpoint"]["created_before_cursor"] is None
    assert artifact["checkpoint"]["resume_required"] is False
    assert "checkpoint_interpretation" in artifact["operator_guidance"]
    assert "stall_recovery" in artifact["operator_guidance"]
    assert artifact["outcomes"][0]["created_before_cursor"] == "2026-02-28T05:00:00+00:00"
    assert artifact["outcomes"][0]["page"] == 1


def test_backfill_persistence_skips_existing_firehose_rows(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    provider = RecordingProvider(
        {
            (
                date(2026, 2, 6),
                date(2026, 3, 8),
                None,
                1,
            ): [
                DiscoveredRepository(
                    github_repository_id=999,
                    owner_login="renamed-owner",
                    repository_name="renamed-repo",
                    full_name="renamed-owner/renamed-repo",
                    created_at=datetime(2026, 2, 28, 15, 0, tzinfo=timezone.utc),
                )
            ],
        }
    )

    with _make_session(tmp_path) as session:
        persist_firehose_batch(
            session,
            [
                DiscoveredRepository(
                    github_repository_id=999,
                    owner_login="octocat",
                    repository_name="repo-999",
                    full_name="octocat/repo-999",
                    created_at=datetime(2026, 2, 28, 15, 0, tzinfo=timezone.utc),
                    firehose_discovery_mode=FirehoseMode.NEW,
                )
            ],
            mode=FirehoseMode.NEW,
        )
        existing = session.get(RepositoryIntake, 999)
        assert existing is not None
        existing.queue_status = RepositoryQueueStatus.COMPLETED
        existing.processing_started_at = datetime(2026, 2, 28, 15, 5, tzinfo=timezone.utc)
        existing.processing_completed_at = datetime(2026, 2, 28, 15, 15, tzinfo=timezone.utc)
        existing.status_updated_at = datetime(2026, 2, 28, 15, 15, tzinfo=timezone.utc)
        original_completed_at = existing.processing_completed_at
        original_status_updated_at = existing.status_updated_at
        session.add(existing)
        session.commit()
        result = run_backfill_job(
            session=session,
            provider=provider,
            runtime_dir=runtime_dir,
            pacing_seconds=1,
            per_page=10,
            pages=1,
            window_days=30,
            min_created_date=date(2008, 1, 1),
            sleep_fn=lambda _seconds: None,
            today=date(2026, 3, 8),
        )
        rows = session.exec(select(RepositoryIntake)).all()

    assert result.status is BackfillRunStatus.SUCCESS
    assert result.outcomes[0].inserted_count == 0
    assert result.outcomes[0].skipped_count == 1
    assert len(rows) == 1
    assert rows[0].discovery_source is RepositoryDiscoverySource.FIREHOSE
    assert rows[0].firehose_discovery_mode is RepositoryFirehoseMode.NEW
    assert rows[0].owner_login == "renamed-owner"
    assert rows[0].repository_name == "renamed-repo"
    assert rows[0].full_name == "renamed-owner/renamed-repo"
    assert rows[0].queue_status is RepositoryQueueStatus.COMPLETED
    assert rows[0].processing_completed_at == original_completed_at
    assert rows[0].status_updated_at == original_status_updated_at

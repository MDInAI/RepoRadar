from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

from sqlmodel import Session, create_engine

from app.core.config import settings
from app.models import (
    AgentRun,
    AgentRunStatus,
    BackfillProgress,
    RepositoryAnalysisStatus,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
    SQLModel,
)
from app.services.agent_runtime_progress_service import AgentRuntimeProgressService


def _make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'runtime-progress.db'}")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_analyst_progress_ignores_stale_running_snapshot_after_pause(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    snapshot_dir = runtime_dir / "analyst"
    snapshot_dir.mkdir(parents=True)
    snapshot_dir.joinpath("progress.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-16T12:00:00+00:00",
                "status_label": "Running batch",
                "current_activity": "Analyzing accepted repositories.",
                "current_target": "Repo #424",
                "completed_count": 12,
                "total_count": 40,
                "remaining_count": 28,
                "unit_label": "repos",
                "source": "analysis queue snapshot",
            }
        ),
        encoding="utf-8",
    )

    with _make_session(tmp_path) as session:
        session.add(
            RepositoryIntake(
                github_repository_id=424,
                owner_login="octocat",
                repository_name="waiting-repo",
                full_name="octocat/waiting-repo",
                repository_description="Pending analysis work",
                stargazers_count=10,
                forks_count=2,
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                firehose_discovery_mode=RepositoryFirehoseMode.NEW,
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.PENDING,
                discovered_at=datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc),
                queue_created_at=datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc),
                status_updated_at=datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc),
                triaged_at=datetime(2026, 3, 16, 10, 5, tzinfo=timezone.utc),
            )
        )
        latest_run = AgentRun(
            agent_name="analyst",
            status=AgentRunStatus.SKIPPED_PAUSED,
            started_at=datetime(2026, 3, 16, 12, 5, tzinfo=timezone.utc),
            completed_at=datetime(2026, 3, 16, 12, 5, tzinfo=timezone.utc),
        )
        session.add(latest_run)
        session.commit()

        service = AgentRuntimeProgressService(session, runtime_dir=runtime_dir)
        progress = service.build_for_agent("analyst", latest_run)

    assert progress.current_activity == "Waiting for accepted repositories that need analysis."
    assert progress.current_target == "1 repos still need analysis work"
    assert progress.status_label == "Idle"


def test_backfill_progress_surfaces_window_page_cursor_and_discovery_counts(tmp_path: Path) -> None:
    total_pages = max(settings.BACKFILL_PAGES, 1)
    with _make_session(tmp_path) as session:
        session.add(
            BackfillProgress(
                window_start_date=date(2025, 12, 12),
                created_before_boundary=date(2026, 1, 11),
                created_before_cursor=datetime(2026, 1, 10, 8, 30, tzinfo=timezone.utc),
                next_page=2,
                pages_processed_in_run=1,
                exhausted=False,
                resume_required=True,
                last_checkpointed_at=datetime(2026, 3, 18, 1, 15, tzinfo=timezone.utc),
            )
        )
        session.add(
            RepositoryIntake(
                github_repository_id=1001,
                owner_login="octocat",
                repository_name="history-one",
                full_name="octocat/history-one",
                repository_description="Backfill pending",
                stargazers_count=10,
                forks_count=1,
                discovery_source=RepositoryDiscoverySource.BACKFILL,
                queue_status=RepositoryQueueStatus.PENDING,
                triage_status=RepositoryTriageStatus.PENDING,
                analysis_status=RepositoryAnalysisStatus.PENDING,
                discovered_at=datetime(2026, 1, 10, 8, 0, tzinfo=timezone.utc),
                queue_created_at=datetime(2026, 1, 10, 8, 0, tzinfo=timezone.utc),
                status_updated_at=datetime(2026, 1, 10, 8, 0, tzinfo=timezone.utc),
            )
        )
        session.add(
            RepositoryIntake(
                github_repository_id=1002,
                owner_login="octocat",
                repository_name="history-two",
                full_name="octocat/history-two",
                repository_description="Backfill complete",
                stargazers_count=15,
                forks_count=2,
                discovery_source=RepositoryDiscoverySource.BACKFILL,
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.REJECTED,
                analysis_status=RepositoryAnalysisStatus.PENDING,
                discovered_at=datetime(2026, 1, 10, 7, 0, tzinfo=timezone.utc),
                queue_created_at=datetime(2026, 1, 10, 7, 0, tzinfo=timezone.utc),
                status_updated_at=datetime(2026, 1, 10, 7, 0, tzinfo=timezone.utc),
            )
        )
        latest_run = AgentRun(
            agent_name="backfill",
            status=AgentRunStatus.RUNNING,
            started_at=datetime(2026, 3, 18, 1, 0, tzinfo=timezone.utc),
        )
        session.add(latest_run)
        session.commit()

        service = AgentRuntimeProgressService(session)
        progress = service.build_for_agent("backfill", latest_run)

    assert progress.current_activity == "Scanning historical repositories created in 2025-12-12 through 2026-01-10."
    assert progress.current_target == (
        f"Window 2025-12-12 through 2026-01-10 · page 2 of {total_pages} · cursor 2026-01-10T08:30:00+00:00"
    )
    assert progress.primary_counts_label == "Pages completed in this historical window"
    assert progress.completed_count == 1
    assert progress.total_count == total_pages
    assert progress.remaining_count == total_pages - 1
    assert "Current historical window: 2025-12-12 through 2026-01-10" in progress.details
    assert f"Resume page: 2 of {total_pages}" in progress.details
    assert "Cursor inside current window: 2026-01-10T08:30:00+00:00" in progress.details
    assert "Backfill repos discovered so far: 2" in progress.details
    assert "Backfill repos still waiting downstream: 1" in progress.details

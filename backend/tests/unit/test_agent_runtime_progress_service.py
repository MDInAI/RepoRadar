from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from sqlmodel import Session, create_engine

from app.models import (
    AgentRun,
    AgentRunStatus,
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

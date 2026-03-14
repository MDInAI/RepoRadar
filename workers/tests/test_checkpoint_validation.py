from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine, select

from agentic_workers.core.recovery import validate_startup_recovery
from agentic_workers.storage.backend_models import (
    BackfillProgress,
    FirehoseProgress,
    RepositoryAnalysisStatus,
    RepositoryIntake,
    RepositoryTriageStatus,
    SQLModel,
    SystemEvent,
)
from agentic_workers.storage.backfill_progress import save_backfill_progress, BackfillCheckpointState
from agentic_workers.storage.firehose_progress import save_firehose_progress, FirehoseCheckpointState
from agentic_workers.providers.github_provider import FirehoseMode


def _make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'recovery.db'}")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_validate_startup_with_no_checkpoints(tmp_path: Path):
    """Startup validation succeeds when no checkpoints exist."""
    with _make_session(tmp_path) as session:
        validate_startup_recovery(session)


def test_validate_startup_with_valid_firehose_checkpoint(tmp_path: Path):
    """Startup validation succeeds with valid Firehose checkpoint."""
    with _make_session(tmp_path) as session:
        checkpoint = FirehoseCheckpointState(
            source_provider="github",
            active_mode=FirehoseMode.NEW,
            next_page=3,
            new_anchor_date=date.today() - timedelta(days=1),
            trending_anchor_date=date.today() - timedelta(days=7),
            run_started_at=datetime.now(timezone.utc),
            resume_required=True,
            last_checkpointed_at=datetime.now(timezone.utc),
        )
        save_firehose_progress(session, checkpoint)
        validate_startup_recovery(session)
        events = session.exec(select(SystemEvent).where(SystemEvent.event_type == "worker_recovered", SystemEvent.agent_name == "firehose")).all()
        assert len(events) == 1
        assert "page 3" in events[0].message


def test_validate_startup_with_valid_backfill_checkpoint(tmp_path: Path):
    """Startup validation succeeds with valid Backfill checkpoint."""
    with _make_session(tmp_path) as session:
        checkpoint = BackfillCheckpointState(
            source_provider="github",
            window_start_date=date.today() - timedelta(days=30),
            created_before_boundary=date.today(),
            created_before_cursor=None,
            next_page=5,
            exhausted=False,
            last_checkpointed_at=datetime.now(timezone.utc),
            resume_required=True,
        )
        save_backfill_progress(session, checkpoint)
        validate_startup_recovery(session)
        events = session.exec(select(SystemEvent).where(SystemEvent.event_type == "worker_recovered", SystemEvent.agent_name == "backfill")).all()
        assert len(events) == 1
        assert "page 5" in events[0].message


def test_reset_stale_in_progress_states(tmp_path: Path):
    """Startup validation resets stale in_progress queue items to pending."""
    with _make_session(tmp_path) as session:
        from agentic_workers.storage.backend_models import RepositoryQueueStatus
        repo = RepositoryIntake(
            github_repository_id=99999,
            full_name="test/stale",
            owner_login="test",
            repository_name="stale",
            source_provider="github",
            discovery_source="firehose",
            firehose_discovery_mode="new",
            queue_status=RepositoryQueueStatus.IN_PROGRESS,
            triage_status=RepositoryTriageStatus.PENDING,
            analysis_status=RepositoryAnalysisStatus.PENDING,
        )
        session.add(repo)
        session.commit()

        validate_startup_recovery(session)

        updated = session.exec(select(RepositoryIntake).where(RepositoryIntake.github_repository_id == 99999)).one()
        assert updated.queue_status == RepositoryQueueStatus.PENDING



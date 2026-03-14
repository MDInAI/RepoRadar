from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine, select

from agentic_workers.storage.backend_models import SQLModel
from agentic_workers.storage.backfill_progress import load_backfill_progress, save_backfill_progress, BackfillCheckpointState
from agentic_workers.storage.firehose_progress import load_firehose_progress, save_firehose_progress, FirehoseCheckpointState
from agentic_workers.providers.github_provider import FirehoseMode


def _make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'crash.db'}")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_firehose_recovery_resumes_from_checkpoint(tmp_path: Path):
    """Firehose resumes from persisted checkpoint after simulated restart."""
    with _make_session(tmp_path) as session:
        checkpoint = FirehoseCheckpointState(
            source_provider="github",
            active_mode=FirehoseMode.NEW,
            next_page=5,
            new_anchor_date=date.today() - timedelta(days=1),
            trending_anchor_date=date.today() - timedelta(days=7),
            run_started_at=datetime.now(timezone.utc),
            resume_required=True,
            last_checkpointed_at=datetime.now(timezone.utc),
        )
        save_firehose_progress(session, checkpoint)
        loaded = load_firehose_progress(session)
        assert loaded is not None
        assert loaded.resume_required is True
        assert loaded.next_page == 5
        assert loaded.active_mode == FirehoseMode.NEW


def test_backfill_recovery_resumes_from_checkpoint(tmp_path: Path):
    """Backfill resumes from persisted checkpoint after simulated restart."""
    with _make_session(tmp_path) as session:
        checkpoint = BackfillCheckpointState(
            source_provider="github",
            window_start_date=date.today() - timedelta(days=30),
            created_before_boundary=date.today(),
            created_before_cursor=None,
            next_page=10,
            exhausted=False,
            last_checkpointed_at=datetime.now(timezone.utc),
            resume_required=True,
        )
        save_backfill_progress(session, checkpoint)
        loaded = load_backfill_progress(session)
        assert loaded is not None
        assert loaded.resume_required is True
        assert loaded.next_page == 10

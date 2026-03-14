from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine, select

from agentic_workers.storage.backend_models import (
    RepositoryAnalysisStatus,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
    SQLModel,
)


def _make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'queue.db'}")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_bouncer_recovery_resumes_pending_triage(tmp_path: Path):
    """Bouncer resumes processing pending triage items after restart."""
    with _make_session(tmp_path) as session:
        repo = RepositoryIntake(
            github_repository_id=12345,
            full_name="test/repo",
            owner_login="test",
            repository_name="repo",
            source_provider="github",
            discovery_source="firehose",
            firehose_discovery_mode="new",
            queue_status=RepositoryQueueStatus.PENDING,
            triage_status=RepositoryTriageStatus.PENDING,
            analysis_status=RepositoryAnalysisStatus.PENDING,
        )
        session.add(repo)
        session.commit()
        pending = session.exec(
            select(RepositoryIntake).where(
                RepositoryIntake.queue_status == RepositoryQueueStatus.PENDING,
                RepositoryIntake.triage_status == RepositoryTriageStatus.PENDING,
            )
        ).all()
        assert len(pending) == 1
        assert pending[0].github_repository_id == 12345


def test_analyst_recovery_resumes_pending_analysis(tmp_path: Path):
    """Analyst resumes processing pending analysis items after restart."""
    with _make_session(tmp_path) as session:
        repo = RepositoryIntake(
            github_repository_id=67890,
            full_name="test/another",
            owner_login="test",
            repository_name="another",
            source_provider="github",
            discovery_source="firehose",
            firehose_discovery_mode="trending",
            queue_status=RepositoryQueueStatus.PENDING,
            triage_status=RepositoryTriageStatus.ACCEPTED,
            analysis_status=RepositoryAnalysisStatus.PENDING,
        )
        session.add(repo)
        session.commit()
        pending = session.exec(
            select(RepositoryIntake).where(
                RepositoryIntake.triage_status == RepositoryTriageStatus.ACCEPTED,
                RepositoryIntake.analysis_status == RepositoryAnalysisStatus.PENDING,
            )
        ).all()
        assert len(pending) == 1
        assert pending[0].github_repository_id == 67890

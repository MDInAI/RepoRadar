from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from agentic_workers.jobs.combiner_job import CombinerRunStatus, run_combiner_job
from agentic_workers.storage.backend_models import (
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryArtifactPayload,
    RepositoryIntake,
    SynthesisRun,
    SynthesisRunStatus,
    SynthesisRunType,
)


def _make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'combiner-job.db'}")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_combiner_job_reads_readme_payloads_from_database_without_legacy_files(
    tmp_path: Path,
) -> None:
    with _make_session(tmp_path) as session:
        now = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        session.add(
            RepositoryIntake(
                github_repository_id=701,
                owner_login="octocat",
                repository_name="readme-source",
                full_name="octocat/readme-source",
            )
        )
        session.add(
            RepositoryArtifact(
                github_repository_id=701,
                artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                runtime_relative_path="data/readmes/701.md",
                content_sha256="a" * 64,
                byte_size=128,
                content_type="text/markdown",
                source_kind="repository_readme",
                generated_at=now,
            )
        )
        session.add(
            RepositoryArtifactPayload(
                github_repository_id=701,
                artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                content_text="# Product\n\nWorkflow automation and analytics.",
                updated_at=now,
            )
        )
        session.add(
            SynthesisRun(
                run_type=SynthesisRunType.COMBINER,
                status=SynthesisRunStatus.PENDING,
                input_repository_ids=[701],
            )
        )
        session.commit()

        result = run_combiner_job(session=session, runtime_dir=tmp_path / "runtime")
        run = session.exec(select(SynthesisRun).where(SynthesisRun.run_type == SynthesisRunType.COMBINER)).first()

    assert result.status is CombinerRunStatus.SUCCESS
    assert run is not None
    assert run.status is SynthesisRunStatus.COMPLETED
    assert run.output_text is not None
    assert "workflow automation" in run.output_text.lower()

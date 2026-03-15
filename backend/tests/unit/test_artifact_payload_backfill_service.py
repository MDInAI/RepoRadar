from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.models import (
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryArtifactPayload,
    RepositoryIntake,
)
from app.repositories.repository_artifact_payload_repository import (
    RepositoryArtifactPayloadRepository,
)
from app.services.artifact_payload_backfill_service import ArtifactPayloadBackfillService


def _make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'artifact-payload-backfill.db'}")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_backfill_service_imports_missing_payloads_from_legacy_files(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    now = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)

    with _make_session(tmp_path) as session:
        session.add(
            RepositoryIntake(
                github_repository_id=701,
                owner_login="octocat",
                repository_name="artifact-import",
                full_name="octocat/artifact-import",
            )
        )
        session.add(
            RepositoryArtifact(
                github_repository_id=701,
                artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                runtime_relative_path="data/readmes/701.md",
                content_sha256="a" * 64,
                byte_size=100,
                content_type="text/markdown",
                source_kind="repository_readme",
                generated_at=now,
            )
        )
        session.commit()

        legacy_path = runtime_dir / "data" / "readmes" / "701.md"
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text("# Imported\n\nPayload", encoding="utf-8")

        repository = RepositoryArtifactPayloadRepository(session, runtime_dir=runtime_dir)
        service = ArtifactPayloadBackfillService(session, repository)

        result = service.backfill()
        payload_row = session.get(
            RepositoryArtifactPayload,
            (701, RepositoryArtifactKind.README_SNAPSHOT),
        )

    assert result.scanned == 1
    assert result.imported == 1
    assert result.skipped_existing == 0
    assert result.missing_legacy_file == 0
    assert payload_row is not None
    assert payload_row.content_text == "# Imported\n\nPayload"


def test_backfill_service_skips_existing_payloads_and_missing_files(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    now = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)

    with _make_session(tmp_path) as session:
        session.add_all(
            [
                RepositoryIntake(
                    github_repository_id=801,
                    owner_login="octocat",
                    repository_name="has-payload",
                    full_name="octocat/has-payload",
                ),
                RepositoryIntake(
                    github_repository_id=802,
                    owner_login="octocat",
                    repository_name="missing-file",
                    full_name="octocat/missing-file",
                ),
            ]
        )
        session.add_all(
            [
                RepositoryArtifact(
                    github_repository_id=801,
                    artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                    runtime_relative_path="data/readmes/801.md",
                    content_sha256="a" * 64,
                    byte_size=100,
                    content_type="text/markdown",
                    source_kind="repository_readme",
                    generated_at=now,
                ),
                RepositoryArtifact(
                    github_repository_id=802,
                    artifact_kind=RepositoryArtifactKind.ANALYSIS_RESULT,
                    runtime_relative_path="data/analyses/802.json",
                    content_sha256="b" * 64,
                    byte_size=100,
                    content_type="application/json",
                    source_kind="repository_analysis",
                    generated_at=now,
                ),
                RepositoryArtifactPayload(
                    github_repository_id=801,
                    artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                    content_text="already here",
                    updated_at=now,
                ),
            ]
        )
        session.commit()

        repository = RepositoryArtifactPayloadRepository(session, runtime_dir=runtime_dir)
        service = ArtifactPayloadBackfillService(session, repository)

        result = service.backfill()

    assert result.scanned == 2
    assert result.imported == 0
    assert result.skipped_existing == 1
    assert result.missing_legacy_file == 1

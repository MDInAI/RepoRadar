from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

import app.services.artifact_storage_status_service as status_module
from app.models import RepositoryArtifact, RepositoryArtifactKind, RepositoryArtifactPayload, RepositoryIntake
from app.services.artifact_storage_status_service import ArtifactStorageStatusService


def _make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'artifact-storage-status.db'}")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_artifact_storage_status_reports_payload_coverage_and_prune_safety(tmp_path: Path, monkeypatch) -> None:
    runtime_dir = tmp_path / "runtime"
    now = datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc)
    (runtime_dir / "data" / "readmes").mkdir(parents=True, exist_ok=True)
    (runtime_dir / "data" / "analyses").mkdir(parents=True, exist_ok=True)
    (runtime_dir / "data" / "readmes" / "701.md").write_text("# README", encoding="utf-8")
    (runtime_dir / "data" / "analyses" / "701.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(status_module.settings, "ARTIFACT_DEBUG_MIRROR", False)

    with _make_session(tmp_path) as session:
        session.add(
            RepositoryIntake(
                github_repository_id=701,
                owner_login="octocat",
                repository_name="artifact-status",
                full_name="octocat/artifact-status",
            )
        )
        session.add_all(
            [
                RepositoryArtifact(
                    github_repository_id=701,
                    artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                    runtime_relative_path="data/readmes/701.md",
                    content_sha256="a" * 64,
                    byte_size=10,
                    content_type="text/markdown",
                    source_kind="repository_readme",
                    generated_at=now,
                ),
                RepositoryArtifact(
                    github_repository_id=701,
                    artifact_kind=RepositoryArtifactKind.ANALYSIS_RESULT,
                    runtime_relative_path="data/analyses/701.json",
                    content_sha256="b" * 64,
                    byte_size=2,
                    content_type="application/json",
                    source_kind="repository_analysis",
                    generated_at=now,
                ),
                RepositoryArtifactPayload(
                    github_repository_id=701,
                    artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                    content_text="# README",
                    updated_at=now,
                ),
                RepositoryArtifactPayload(
                    github_repository_id=701,
                    artifact_kind=RepositoryArtifactKind.ANALYSIS_RESULT,
                    content_text="{}",
                    updated_at=now,
                ),
            ]
        )
        session.commit()

        status = ArtifactStorageStatusService(session, runtime_dir=runtime_dir).get_status()

    assert status.artifact_metadata_count == 2
    assert status.artifact_payload_count == 2
    assert status.missing_payload_count == 0
    assert status.payload_coverage_percent == 100
    assert status.legacy_readme_file_count == 1
    assert status.legacy_analysis_file_count == 1
    assert status.safe_to_prune_legacy_files is True


def test_artifact_storage_status_blocks_prune_when_debug_mirror_or_missing_payloads(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_module.settings, "ARTIFACT_DEBUG_MIRROR", True)
    now = datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc)

    with _make_session(tmp_path) as session:
        session.add(
            RepositoryIntake(
                github_repository_id=801,
                owner_login="octocat",
                repository_name="missing-payload",
                full_name="octocat/missing-payload",
            )
        )
        session.add(
            RepositoryArtifact(
                github_repository_id=801,
                artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                runtime_relative_path="data/readmes/801.md",
                content_sha256="a" * 64,
                byte_size=10,
                content_type="text/markdown",
                source_kind="repository_readme",
                generated_at=now,
            )
        )
        session.commit()

        status = ArtifactStorageStatusService(session, runtime_dir=tmp_path / "runtime").get_status()

    assert status.artifact_metadata_count == 1
    assert status.artifact_payload_count == 0
    assert status.missing_payload_count == 1
    assert status.safe_to_prune_legacy_files is False
    assert "Turn off ARTIFACT_DEBUG_MIRROR" in status.prune_readiness_reason

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, create_engine

from agentic_workers.core.config import settings
from agentic_workers.storage.analysis_store import (
    _filter_changed_artifacts,
    list_pending_analysis_targets,
)
from agentic_workers.storage.artifact_store import build_text_artifact
from agentic_workers.storage.backend_models import (
    AnalystSourceSettings,
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryAnalysisStatus,
    RepositoryIntake,
    RepositoryTriageStatus,
    RepositoryUserCuration,
    SQLModel,
)


def _make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'analysis-store.db'}")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(AnalystSourceSettings(id=1, firehose_enabled=True, backfill_enabled=False))
    session.commit()
    return session


def _make_repo(
    github_repository_id: int,
    full_name: str,
    description: str | None,
    *,
    triage_status: RepositoryTriageStatus = RepositoryTriageStatus.ACCEPTED,
    analysis_status: RepositoryAnalysisStatus = RepositoryAnalysisStatus.PENDING,
) -> RepositoryIntake:
    owner_login, repository_name = full_name.split("/", 1)
    return RepositoryIntake(
        github_repository_id=github_repository_id,
        owner_login=owner_login,
        repository_name=repository_name,
        full_name=full_name,
        repository_description=description,
        triage_status=triage_status,
        analysis_status=analysis_status,
    )


def test_list_pending_analysis_targets_returns_all_accepted_repos_when_no_keywords_configured(
    tmp_path: Path,
) -> None:
    original_keywords = settings.ANALYST_SELECTION_KEYWORDS
    settings.ANALYST_SELECTION_KEYWORDS = ()
    try:
        with _make_session(tmp_path) as session:
            session.add(
                _make_repo(
                    101,
                    "octocat/workflow-tool",
                    "Workflow automation for teams",
                )
            )
            session.add(
                _make_repo(
                    102,
                    "octocat/medical-bot",
                    "Medical assistant",
                )
            )
            session.commit()

            targets = list_pending_analysis_targets(session)
    finally:
        settings.ANALYST_SELECTION_KEYWORDS = original_keywords

    assert [repo.github_repository_id for repo in targets] == [101, 102]


def test_list_pending_analysis_targets_applies_keyword_gate_and_starred_bypass(
    tmp_path: Path,
) -> None:
    original_keywords = settings.ANALYST_SELECTION_KEYWORDS
    settings.ANALYST_SELECTION_KEYWORDS = ("medical", "workflow")
    try:
        with _make_session(tmp_path) as session:
            session.add(
                _make_repo(
                    201,
                    "FreedomIntelligence/OpenClaw-Medical-Skills",
                    "Medical workflow repo for agentic triage",
                )
            )
            session.add(
                _make_repo(
                    202,
                    "octocat/manual-pick",
                    "General utility repo without matching keywords",
                )
            )
            session.add(
                RepositoryUserCuration(
                    github_repository_id=202,
                    is_starred=True,
                )
            )
            session.add(
                _make_repo(
                    203,
                    "octocat/no-match",
                    "General utility repo without matching keywords",
                )
            )
            session.commit()

            targets = list_pending_analysis_targets(session)
    finally:
        settings.ANALYST_SELECTION_KEYWORDS = original_keywords

    assert [repo.github_repository_id for repo in targets] == [201, 202]


def test_filter_changed_artifacts_skips_identical_hash_matches(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        session.add(_make_repo(301, "octocat/repo-301", "Storage test"))
        session.add(
            RepositoryArtifact(
                github_repository_id=301,
                artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                runtime_relative_path="data/readmes/301.md",
                content_sha256="a" * 64,
                byte_size=12,
                content_type="text/markdown",
                source_kind="repository_readme",
                generated_at=datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc),
            )
        )
        session.commit()

        same_artifact = build_text_artifact(
            runtime_relative_path="data/readmes/301.md",
            artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
            content="same payload",
            content_type="text/markdown",
            source_kind="repository_readme",
            source_url=None,
            provenance_metadata={},
            generated_at=datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc),
        )
        different_artifact = build_text_artifact(
            runtime_relative_path="data/analyses/301.json",
            artifact_kind=RepositoryArtifactKind.ANALYSIS_RESULT,
            content='{"fresh":true}',
            content_type="application/json",
            source_kind="repository_analysis",
            source_url=None,
            provenance_metadata={},
            generated_at=datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc),
        )

        existing = session.get(RepositoryArtifact, (301, RepositoryArtifactKind.README_SNAPSHOT))
        assert existing is not None
        existing.content_sha256 = same_artifact.content_sha256
        existing.byte_size = same_artifact.byte_size
        session.add(existing)
        session.commit()

        changed = _filter_changed_artifacts(
            session,
            repository_id=301,
            artifacts=[same_artifact, different_artifact],
        )

    assert [artifact.artifact_kind for artifact in changed] == [RepositoryArtifactKind.ANALYSIS_RESULT]

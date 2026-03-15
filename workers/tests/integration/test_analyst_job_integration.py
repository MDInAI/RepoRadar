from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine, select

import agentic_workers.jobs.analyst_job as analyst_job_module
import agentic_workers.storage.analysis_store as analysis_store_module
from agentic_workers.jobs.analyst_job import AnalystRunStatus, run_analyst_job
from agentic_workers.providers.github_provider import RepositoryReadme
from agentic_workers.storage.backend_models import (
    RepositoryAnalysisFailureCode,
    RepositoryAnalysisResult,
    RepositoryAnalysisStatus,
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryArtifactPayload,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
    SQLModel,
)


class StubGitHubProvider:
    def __init__(self, readme: RepositoryReadme) -> None:
        self.readme = readme

    def get_readme(self, *, owner_login: str, repository_name: str) -> RepositoryReadme:
        assert owner_login == self.readme.owner_login
        assert repository_name == self.readme.repository_name
        return self.readme


class StaticAnalysisProvider:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def analyze(self, *, repository_full_name: str, readme: object) -> str:
        return self.payload


def _make_session(tmp_path: Path) -> Session:
    database_url = f"sqlite:///{tmp_path / 'analyst-integration.db'}"
    engine = create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _accepted_row(repository_id: int, full_name: str) -> RepositoryIntake:
    owner_login, repository_name = full_name.split("/", maxsplit=1)
    now = datetime(2026, 3, 8, 12, repository_id % 60, tzinfo=timezone.utc)
    return RepositoryIntake(
        github_repository_id=repository_id,
        owner_login=owner_login,
        repository_name=repository_name,
        full_name=full_name,
        repository_description="Automation platform for SaaS teams",
        queue_status=RepositoryQueueStatus.COMPLETED,
        triage_status=RepositoryTriageStatus.ACCEPTED,
        discovered_at=now,
        queue_created_at=now,
        status_updated_at=now,
        triaged_at=now,
    )


def test_analyst_job_success_persists_result_and_runtime_artifacts(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    provider = StubGitHubProvider(
        RepositoryReadme(
            owner_login="octocat",
            repository_name="analyze-me",
            content="# Product\n\nTeam workflow automation with analytics and API access.",
            fetched_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
            source_url="https://api.github.com/repos/octocat/analyze-me/readme",
        )
    )
    analysis_provider = StaticAnalysisProvider(
        '{"monetization_potential":"high","pros":["API surface"],'
        '"cons":["Pricing unclear"],"missing_feature_signals":["Missing billing"]}'
    )

    with _make_session(tmp_path) as session:
        session.add(_accepted_row(707, "octocat/analyze-me"))
        session.commit()

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=runtime_dir,
            analysis_provider=analysis_provider,
        )
        row = session.get(RepositoryIntake, 707)
        analysis_row = session.get(RepositoryAnalysisResult, 707)
        artifact_rows = session.exec(
            select(RepositoryArtifact).order_by(RepositoryArtifact.artifact_kind)
        ).all()
        artifact_payload_rows = session.exec(
            select(RepositoryArtifactPayload).order_by(RepositoryArtifactPayload.artifact_kind)
        ).all()

    assert result.status is AnalystRunStatus.SUCCESS
    assert row is not None
    assert row.analysis_status is RepositoryAnalysisStatus.COMPLETED
    assert analysis_row is not None
    assert analysis_row.monetization_potential.value == "high"
    assert analysis_row.missing_feature_signals == ["Missing billing"]
    assert analysis_row.source_metadata["readme_artifact_path"] == "data/readmes/707.md"
    assert analysis_row.source_metadata["analysis_artifact_path"] == "data/analyses/707.json"

    assert [(row.github_repository_id, row.artifact_kind) for row in artifact_rows] == [
        (707, RepositoryArtifactKind.ANALYSIS_RESULT),
        (707, RepositoryArtifactKind.README_SNAPSHOT),
    ]
    assert [(row.github_repository_id, row.artifact_kind) for row in artifact_payload_rows] == [
        (707, RepositoryArtifactKind.ANALYSIS_RESULT),
        (707, RepositoryArtifactKind.README_SNAPSHOT),
    ]
    readme_payload = next(
        row for row in artifact_payload_rows if row.artifact_kind is RepositoryArtifactKind.README_SNAPSHOT
    )
    analysis_payload_row = next(
        row for row in artifact_payload_rows if row.artifact_kind is RepositoryArtifactKind.ANALYSIS_RESULT
    )
    assert "workflow automation" in readme_payload.content_text
    analysis_payload = json.loads(analysis_payload_row.content_text)
    assert analysis_payload["analysis"]["monetization_potential"] == "high"
    assert analysis_payload["source"]["readme_artifact_path"] == "data/readmes/707.md"
    assert not (runtime_dir / "data" / "readmes" / "707.md").exists()
    assert not (runtime_dir / "data" / "analyses" / "707.json").exists()

    artifact = json.loads(result.artifact_path.read_text())  # type: ignore[union-attr]
    assert artifact["status"] == "success"
    assert artifact["summary"] == {"completed": 1, "failed": 0}
    assert artifact["outcomes"][0]["runtime_readme_artifact_path"] == "data/readmes/707.md"
    assert artifact["outcomes"][0]["runtime_analysis_artifact_path"] == "data/analyses/707.json"


def test_analyst_job_persistence_failure_does_not_leave_completed_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = StubGitHubProvider(
        RepositoryReadme(
            owner_login="octocat",
            repository_name="db-failure",
            content="# Product\n\nWorkflow automation with analytics and API access.",
            fetched_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
            source_url="https://api.github.com/repos/octocat/db-failure/readme",
        )
    )

    def fail_persist_success(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("database write failed")

    monkeypatch.setattr(analyst_job_module, "persist_analysis_success", fail_persist_success)

    with _make_session(tmp_path) as session:
        session.add(_accepted_row(808, "octocat/db-failure"))
        session.commit()

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
            analysis_provider=StaticAnalysisProvider(
                '{"monetization_potential":"medium","pros":["Automation"],'
                '"cons":["Pricing unclear"],"missing_feature_signals":["Missing billing"]}'
            ),
        )
        row = session.get(RepositoryIntake, 808)
        analysis_row = session.get(RepositoryAnalysisResult, 808)

    assert result.status is AnalystRunStatus.FAILED
    assert row is not None
    assert row.analysis_status is RepositoryAnalysisStatus.FAILED
    assert row.analysis_failure_code is RepositoryAnalysisFailureCode.PERSISTENCE_ERROR
    assert analysis_row is None


def test_analyst_job_restores_previous_artifacts_when_db_persistence_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_dir = tmp_path / "runtime"
    readme_path = runtime_dir / "data" / "readmes" / "909.md"
    analysis_path = runtime_dir / "data" / "analyses" / "909.json"
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    analysis_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text("old snapshot", encoding="utf-8")
    analysis_path.write_text('{"analysis":{"monetization_potential":"low"}}\n', encoding="utf-8")

    provider = StubGitHubProvider(
        RepositoryReadme(
            owner_login="octocat",
            repository_name="rollback-check",
            content="# Product\n\nWorkflow automation with analytics and API access.",
            fetched_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
            source_url="https://api.github.com/repos/octocat/rollback-check/readme",
        )
    )

    original_commit = Session.commit
    commit_calls = {"count": 0}

    def fail_second_commit(self: Session) -> None:
        commit_calls["count"] += 1
        if commit_calls["count"] == 2:
            raise RuntimeError("database write failed")
        original_commit(self)

    monkeypatch.setattr(Session, "commit", fail_second_commit)

    with _make_session(tmp_path) as session:
        session.add(_accepted_row(909, "octocat/rollback-check"))
        session.commit()

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=runtime_dir,
            analysis_provider=StaticAnalysisProvider(
                '{"monetization_potential":"medium","pros":["Automation"],'
                '"cons":["Pricing unclear"],"missing_feature_signals":["Missing billing"]}'
            ),
        )
        row = session.get(RepositoryIntake, 909)
        analysis_row = session.get(RepositoryAnalysisResult, 909)
        artifact_rows = session.exec(select(RepositoryArtifact)).all()

    assert result.status is AnalystRunStatus.FAILED
    assert row is not None
    assert row.analysis_status is RepositoryAnalysisStatus.FAILED
    assert row.analysis_failure_code is RepositoryAnalysisFailureCode.PERSISTENCE_ERROR
    assert analysis_row is None
    assert artifact_rows == []
    assert readme_path.read_text(encoding="utf-8") == "old snapshot"
    assert json.loads(analysis_path.read_text(encoding="utf-8"))["analysis"][
        "monetization_potential"
    ] == "low"


def test_analyst_job_writes_optional_debug_mirror_when_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_dir = tmp_path / "runtime"
    provider = StubGitHubProvider(
        RepositoryReadme(
            owner_login="octocat",
            repository_name="mirror-check",
            content="# Product\n\nWorkflow automation with analytics and API access.",
            fetched_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
            source_url="https://api.github.com/repos/octocat/mirror-check/readme",
        )
    )
    analysis_provider = StaticAnalysisProvider(
        '{"monetization_potential":"high","pros":["API surface"],'
        '"cons":["Pricing unclear"],"missing_feature_signals":["Missing billing"]}'
    )
    monkeypatch.setattr(analysis_store_module.settings, "ARTIFACT_DEBUG_MIRROR", True)

    with _make_session(tmp_path) as session:
        session.add(_accepted_row(919, "octocat/mirror-check"))
        session.commit()

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=runtime_dir,
            analysis_provider=analysis_provider,
        )

    assert result.status is AnalystRunStatus.SUCCESS
    snapshot_path = runtime_dir / "data" / "readmes" / "919.md"
    analysis_path = runtime_dir / "data" / "analyses" / "919.json"
    assert snapshot_path.exists()
    assert analysis_path.exists()

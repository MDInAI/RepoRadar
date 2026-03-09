from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, create_engine, select

from agentic_workers.jobs.analyst_job import AnalystRunStatus, run_analyst_job
from agentic_workers.providers.github_provider import GitHubReadmeNotFoundError, RepositoryReadme
from agentic_workers.storage.backend_models import (
    RepositoryAnalysisFailureCode,
    RepositoryAnalysisResult,
    RepositoryAnalysisStatus,
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
    SQLModel,
)


class StubGitHubProvider:
    def __init__(self, responses: dict[int, RepositoryReadme | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def get_readme(self, *, owner_login: str, repository_name: str) -> RepositoryReadme:
        self.calls.append((owner_login, repository_name))
        for response in self.responses.values():
            if isinstance(response, RepositoryReadme) and (
                response.owner_login == owner_login and response.repository_name == repository_name
            ):
                return response
        response = next(iter(self.responses.values()))
        if isinstance(response, Exception):
            raise response
        return response


class StaticAnalysisProvider:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def analyze(self, *, repository_full_name: str, readme: object) -> str:
        return self.payload


def _make_session(tmp_path: Path) -> Session:
    database_url = f"sqlite:///{tmp_path / 'analyst-unit.db'}"
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
        repository_description="Platform automation for SaaS teams",
        queue_status=RepositoryQueueStatus.COMPLETED,
        triage_status=RepositoryTriageStatus.ACCEPTED,
        discovered_at=now,
        queue_created_at=now,
        status_updated_at=now,
        triaged_at=now,
    )


def test_analyst_job_processes_only_accepted_repositories_without_completed_analysis(
    tmp_path: Path,
) -> None:
    provider = StubGitHubProvider(
        {
            101: RepositoryReadme(
                owner_login="octocat",
                repository_name="analyze-me",
                content="# Product\n\nTeam workflow automation with analytics and API access.",
                fetched_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                source_url="https://api.github.com/repos/octocat/analyze-me/readme",
            )
        }
    )
    analysis_provider = StaticAnalysisProvider(
        '{"monetization_potential":"high","pros":["Clear workflow"],'
        '"cons":["Pricing unclear"],"missing_feature_signals":["Missing billing"]}'
    )

    with _make_session(tmp_path) as session:
        accepted = _accepted_row(101, "octocat/analyze-me")
        already_done = _accepted_row(202, "octocat/already-done")
        already_done.analysis_status = RepositoryAnalysisStatus.COMPLETED
        rejected = _accepted_row(303, "octocat/rejected")
        rejected.triage_status = RepositoryTriageStatus.REJECTED
        pending = _accepted_row(404, "octocat/pending")
        pending.triage_status = RepositoryTriageStatus.PENDING
        session.add(accepted)
        session.add(already_done)
        session.add(rejected)
        session.add(pending)
        session.commit()

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
            analysis_provider=analysis_provider,
        )
        rows = session.exec(
            select(RepositoryIntake).order_by(RepositoryIntake.github_repository_id)
        ).all()
        analysis_rows = session.exec(select(RepositoryAnalysisResult)).all()
        artifact_rows = session.exec(
            select(RepositoryArtifact).order_by(
                RepositoryArtifact.github_repository_id,
                RepositoryArtifact.artifact_kind,
            )
        ).all()

    assert result.status is AnalystRunStatus.SUCCESS
    assert provider.calls == [("octocat", "analyze-me")]
    assert [row.github_repository_id for row in analysis_rows] == [101]
    assert [
        (row.github_repository_id, row.artifact_kind) for row in artifact_rows
    ] == [
        (101, RepositoryArtifactKind.ANALYSIS_RESULT),
        (101, RepositoryArtifactKind.README_SNAPSHOT),
    ]
    assert rows[0].analysis_status is RepositoryAnalysisStatus.COMPLETED
    assert rows[1].analysis_status is RepositoryAnalysisStatus.COMPLETED
    assert rows[2].analysis_status is RepositoryAnalysisStatus.PENDING
    assert rows[3].analysis_status is RepositoryAnalysisStatus.PENDING


def test_analyst_job_records_invalid_analysis_output_without_overwriting_unrelated_state(
    tmp_path: Path,
) -> None:
    triaged_at = datetime(2026, 3, 8, 12, 30, tzinfo=timezone.utc)
    provider = StubGitHubProvider(
        {
            505: RepositoryReadme(
                owner_login="octocat",
                repository_name="broken-analysis",
                content="# Product\n\nAnalytics workflow tool.",
                fetched_at=triaged_at,
                source_url="https://api.github.com/repos/octocat/broken-analysis/readme",
            )
        }
    )

    with _make_session(tmp_path) as session:
        row = _accepted_row(505, "octocat/broken-analysis")
        row.repository_description = "Keep this description"
        row.triaged_at = triaged_at
        session.add(row)
        session.commit()

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
            analysis_provider=StaticAnalysisProvider("{not-json"),
        )
        reloaded = session.get(RepositoryIntake, 505)
        analysis_row = session.get(RepositoryAnalysisResult, 505)

    assert result.status is AnalystRunStatus.FAILED
    assert reloaded is not None
    assert reloaded.analysis_status is RepositoryAnalysisStatus.FAILED
    assert reloaded.analysis_failure_code is RepositoryAnalysisFailureCode.INVALID_ANALYSIS_OUTPUT
    assert reloaded.queue_status is RepositoryQueueStatus.COMPLETED
    assert reloaded.triage_status is RepositoryTriageStatus.ACCEPTED
    assert reloaded.repository_description == "Keep this description"
    assert reloaded.triaged_at == triaged_at
    assert analysis_row is None


def test_analyst_job_records_missing_readme_failures_for_retry_review(tmp_path: Path) -> None:
    provider = StubGitHubProvider(
        {606: GitHubReadmeNotFoundError("Repository README not found for octocat/missing")}
    )

    with _make_session(tmp_path) as session:
        session.add(_accepted_row(606, "octocat/missing"))
        session.commit()

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
            analysis_provider=StaticAnalysisProvider(
                '{"monetization_potential":"low","pros":[],"cons":[],"missing_feature_signals":[]}'
            ),
        )
        row = session.get(RepositoryIntake, 606)

    assert result.status is AnalystRunStatus.FAILED
    assert row is not None
    assert row.analysis_status is RepositoryAnalysisStatus.FAILED
    assert row.analysis_failure_code is RepositoryAnalysisFailureCode.MISSING_README


def test_analyst_job_fails_when_durable_artifact_directories_are_unwritable(
    tmp_path: Path,
) -> None:
    provider = StubGitHubProvider(
        {
            707: RepositoryReadme(
                owner_login="octocat",
                repository_name="artifact-failure",
                content="# Product\n\nWorkflow automation with analytics.",
                fetched_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                source_url="https://api.github.com/repos/octocat/artifact-failure/readme",
            )
        }
    )
    runtime_dir = tmp_path / "runtime"
    (runtime_dir / "data").mkdir(parents=True)
    (runtime_dir / "data" / "readmes").write_text("not-a-directory", encoding="utf-8")

    with _make_session(tmp_path) as session:
        session.add(_accepted_row(707, "octocat/artifact-failure"))
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
        row = session.get(RepositoryIntake, 707)
        analysis_row = session.get(RepositoryAnalysisResult, 707)

    assert result.status is AnalystRunStatus.FAILED
    assert row is not None
    assert row.analysis_status is RepositoryAnalysisStatus.FAILED
    assert row.analysis_failure_code is RepositoryAnalysisFailureCode.PERSISTENCE_ERROR
    assert analysis_row is None

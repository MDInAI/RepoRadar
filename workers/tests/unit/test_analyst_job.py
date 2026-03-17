from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import agentic_workers.jobs.analyst_job as analyst_job_module
import agentic_workers.storage.analysis_store as analysis_store_module
from sqlmodel import Session, create_engine, select

from agentic_workers.jobs.analyst_job import AnalystRunStatus, run_analyst_job
from agentic_workers.providers.github_provider import (
    GitHubProviderError,
    GitHubRateLimitError,
    GitHubReadmeNotFoundError,
    RepositoryReadme,
)
from agentic_workers.providers.readme_analyst import ReadmeAnalysisUsage
from agentic_workers.storage.backend_models import (
    AgentPauseState,
    AgentRun,
    AgentRunStatus,
    FailureClassification,
    FailureSeverity,
    RepositoryCategory,
    RepositoryAnalysisFailureCode,
    RepositoryAnalysisResult,
    RepositoryAnalysisStatus,
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
    SQLModel,
    SystemEvent,
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
    provider_name = "static-analysis"
    model_name = "static-model"

    def __init__(self, payload: str, *, usage: ReadmeAnalysisUsage | None = None) -> None:
        self.payload = payload
        self.last_usage = usage or ReadmeAnalysisUsage()

    def analyze(
        self,
        *,
        repository_full_name: str,
        readme: object,
        evidence: dict[str, object] | None = None,
    ) -> str:
        del repository_full_name, readme, evidence
        return self.payload


class RaisingAnalysisProvider:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def analyze(
        self,
        *,
        repository_full_name: str,
        readme: object,
        evidence: dict[str, object] | None = None,
    ) -> str:
        del repository_full_name, readme, evidence
        raise self.error


class FakeRateLimitError(Exception):
    def __init__(self, message: str, *, status_code: int, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


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


def _current_analysis_row(repository_id: int) -> RepositoryAnalysisResult:
    analyzed_at = datetime(2026, 3, 8, 13, repository_id % 60, tzinfo=timezone.utc)
    return RepositoryAnalysisResult(
        github_repository_id=repository_id,
        source_provider="github",
        source_kind="repository_readme",
        source_metadata={
            "analysis_schema_version": analysis_store_module.CURRENT_ANALYSIS_SCHEMA_VERSION,
            "analysis_mode": "fast",
            "analysis_outcome": "completed",
            "analysis_evidence_version": "fast-evidence-v1",
            "analysis_summary_short": "Current evidence-backed analysis is present.",
            "score_breakdown": {"technical_maturity_score": 50},
            "analysis_provider": analysis_store_module._expected_analysis_provider_name(),
            "analysis_model_name": analysis_store_module._expected_analysis_model_name(),
        },
        monetization_potential="medium",
        category=RepositoryCategory.WORKFLOW,
        agent_tags=["workflow"],
        analyzed_at=analyzed_at,
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
        session.add(_current_analysis_row(202))
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
    assert sorted(row.github_repository_id for row in analysis_rows) == [101, 202]
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


def test_analyst_job_reprocesses_completed_repositories_with_legacy_analysis_metadata(
    tmp_path: Path,
) -> None:
    provider = StubGitHubProvider(
        {
            111: RepositoryReadme(
                owner_login="octocat",
                repository_name="legacy-analysis",
                content="# Product\n\nTeam workflow automation with analytics and API access.",
                fetched_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                source_url="https://api.github.com/repos/octocat/legacy-analysis/readme",
            )
        }
    )
    analysis_provider = StaticAnalysisProvider(
        '{"monetization_potential":"high","pros":["Clear workflow"],'
        '"cons":["Pricing unclear"],"missing_feature_signals":["Missing billing"]}'
    )

    with _make_session(tmp_path) as session:
        legacy = _accepted_row(111, "octocat/legacy-analysis")
        legacy.analysis_status = RepositoryAnalysisStatus.COMPLETED
        session.add(legacy)
        session.add(
            RepositoryAnalysisResult(
                github_repository_id=111,
                source_provider="github",
                source_kind="repository_readme",
                source_metadata={},
                monetization_potential="low",
                analyzed_at=datetime(2026, 3, 8, 11, 0, tzinfo=timezone.utc),
            )
        )
        session.commit()

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
            analysis_provider=analysis_provider,
        )
        analysis_row = session.get(RepositoryAnalysisResult, 111)

    assert result.status is AnalystRunStatus.SUCCESS
    assert provider.calls == [("octocat", "legacy-analysis")]
    assert analysis_row is not None
    assert (
        analysis_row.source_metadata["analysis_schema_version"]
        == analysis_store_module.CURRENT_ANALYSIS_SCHEMA_VERSION
    )


def test_analyst_job_redirects_unknown_category_to_suggested_categories(
    tmp_path: Path,
) -> None:
    provider = StubGitHubProvider(
        {
            112: RepositoryReadme(
                owner_login="octocat",
                repository_name="unknown-category",
                content="# Product\n\nEducation workflow tooling for teams.",
                fetched_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                source_url="https://api.github.com/repos/octocat/unknown-category/readme",
            )
        }
    )
    analysis_provider = StaticAnalysisProvider(
        '{"category":"education","category_confidence_score":72,'
        '"confidence_score":68,"suggested_new_categories":["edtech"],'
        '"monetization_potential":"medium"}'
    )

    with _make_session(tmp_path) as session:
        session.add(_accepted_row(112, "octocat/unknown-category"))
        session.commit()

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
            analysis_provider=analysis_provider,
        )
        analysis_row = session.get(RepositoryAnalysisResult, 112)
        intake_row = session.get(RepositoryIntake, 112)

    assert result.status is AnalystRunStatus.SUCCESS
    assert analysis_row is not None
    assert analysis_row.category is None
    assert analysis_row.suggested_new_categories == ["education", "edtech"]
    assert analysis_row.source_metadata["analysis_mode"] == "fast"
    assert intake_row is not None
    assert intake_row.analysis_status is RepositoryAnalysisStatus.COMPLETED
    assert analysis_row.source_metadata["analysis_mode"] == "fast"


def test_analyst_job_reprocesses_completed_repositories_when_provider_mode_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider = StubGitHubProvider(
        {
            121: RepositoryReadme(
                owner_login="octocat",
                repository_name="provider-refresh",
                content="# Product\n\nTeam workflow automation with analytics and API access.",
                fetched_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                source_url="https://api.github.com/repos/octocat/provider-refresh/readme",
            )
        }
    )
    analysis_provider = StaticAnalysisProvider(
        '{"monetization_potential":"high","pros":["Clear workflow"],'
        '"cons":["Pricing unclear"],"missing_feature_signals":["Missing billing"]}'
    )

    monkeypatch.setattr(analysis_store_module.settings, "ANALYST_PROVIDER", "gemini")
    monkeypatch.setattr(analysis_store_module.settings, "GEMINI_MODEL_NAME", "google/gemini-2.0-flash-001")

    with _make_session(tmp_path) as session:
        repo = _accepted_row(121, "octocat/provider-refresh")
        repo.analysis_status = RepositoryAnalysisStatus.COMPLETED
        session.add(repo)
        session.add(
            RepositoryAnalysisResult(
                github_repository_id=121,
                source_provider="github",
                source_kind="repository_readme",
                source_metadata={
                    "analysis_schema_version": analysis_store_module.CURRENT_ANALYSIS_SCHEMA_VERSION,
                    "analysis_mode": "fast",
                    "analysis_outcome": "completed",
                    "analysis_evidence_version": "fast-evidence-v1",
                    "analysis_summary_short": "Current evidence-backed analysis is present.",
                    "score_breakdown": {"technical_maturity_score": 50},
                    "analysis_provider": "heuristic-readme-analysis",
                    "analysis_model_name": None,
                },
                monetization_potential="low",
                analyzed_at=datetime(2026, 3, 8, 11, 0, tzinfo=timezone.utc),
            )
        )
        session.commit()

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
            analysis_provider=analysis_provider,
        )
        analysis_row = session.get(RepositoryAnalysisResult, 121)

    assert result.status is AnalystRunStatus.SUCCESS
    assert provider.calls == [("octocat", "provider-refresh")]
    assert analysis_row is not None
    assert analysis_row.source_metadata["analysis_provider"] == "static-analysis"


def test_missing_readme_failure_event_does_not_pause_analyst(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        session.add(_accepted_row(112, "octocat/no-readme"))
        session.commit()

        analyst_job_module._emit_analysis_failure_event(
            session,
            agent_run_id=None,
            repository_id=112,
            full_name="octocat/no-readme",
            failure_code=RepositoryAnalysisFailureCode.MISSING_README,
            message="Repository README not found for octocat/no-readme",
            classification=FailureClassification.BLOCKING,
            failure_severity=FailureSeverity.CRITICAL,
            consecutive_failures=1,
            upstream_provider="github",
        )
        session.commit()

        pause_state = session.get(AgentPauseState, "analyst")
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert pause_state is None
    assert [event.event_type for event in events] == ["repository_analysis_failed"]
    assert events[0].failure_classification is FailureClassification.RETRYABLE
    assert events[0].failure_severity is FailureSeverity.WARNING


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
        pause_state = session.get(AgentPauseState, "analyst")
        failure_event = session.exec(
            select(SystemEvent).where(SystemEvent.event_type == "repository_analysis_failed")
        ).one()

    assert result.status is AnalystRunStatus.FAILED
    assert reloaded is not None
    assert reloaded.analysis_status is RepositoryAnalysisStatus.FAILED
    assert reloaded.analysis_failure_code is RepositoryAnalysisFailureCode.INVALID_ANALYSIS_OUTPUT
    assert reloaded.queue_status is RepositoryQueueStatus.COMPLETED
    assert reloaded.triage_status is RepositoryTriageStatus.ACCEPTED
    assert reloaded.repository_description == "Keep this description"
    assert reloaded.triaged_at == triaged_at
    assert analysis_row is None
    assert pause_state is None
    assert failure_event.failure_classification is FailureClassification.RETRYABLE


def test_analyst_job_completes_with_insufficient_evidence_when_readme_is_missing(tmp_path: Path) -> None:
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
        analysis_row = session.get(RepositoryAnalysisResult, 606)
        events = session.exec(select(SystemEvent)).all()

    assert result.status is AnalystRunStatus.SUCCESS
    assert row is not None
    assert row.analysis_status is RepositoryAnalysisStatus.COMPLETED
    assert row.analysis_failure_code is None
    assert analysis_row is not None
    assert analysis_row.source_kind == "repository_evidence"
    assert analysis_row.source_metadata["analysis_outcome"] == "insufficient_evidence"
    assert analysis_row.source_metadata["insufficient_evidence_reason"]
    assert analysis_row.source_metadata["score_breakdown"]["hosted_gap_score"] >= 0
    assert analysis_row.source_metadata["analysis_summary_short"]
    assert events == []


def test_analyst_job_fails_when_durable_artifact_directories_are_unwritable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(analysis_store_module.settings, "ARTIFACT_DEBUG_MIRROR", True)
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

    assert result.status is AnalystRunStatus.SUCCESS
    assert row is not None
    assert row.analysis_status is RepositoryAnalysisStatus.COMPLETED
    assert row.analysis_failure_code is None
    assert analysis_row is not None


def test_analyst_job_accumulates_and_persists_usage_metadata(tmp_path: Path) -> None:
    provider = StubGitHubProvider(
        {
            718: RepositoryReadme(
                owner_login="octocat",
                repository_name="usage-check",
                content="# Product\n\nWorkflow automation with analytics.",
                fetched_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                source_url="https://api.github.com/repos/octocat/usage-check/readme",
            )
        }
    )
    analysis_provider = StaticAnalysisProvider(
        '{"monetization_potential":"medium","pros":["Automation"],'
        '"cons":["Pricing unclear"],"missing_feature_signals":["Missing billing"]}',
        usage=ReadmeAnalysisUsage(input_tokens=120, output_tokens=45, total_tokens=165),
    )

    with _make_session(tmp_path) as session:
        session.add(_accepted_row(718, "octocat/usage-check"))
        session.commit()

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
            analysis_provider=analysis_provider,
        )
        analysis_row = session.get(RepositoryAnalysisResult, 718)

    assert result.status is AnalystRunStatus.SUCCESS
    assert result.input_tokens == 120
    assert result.output_tokens == 45
    assert result.total_tokens == 165
    assert analysis_row is not None
    assert analysis_row.source_metadata["analysis_provider"] == "static-analysis"
    assert analysis_row.source_metadata["analysis_model_name"] == "static-model"
    assert analysis_row.source_metadata["input_tokens"] == 120
    assert analysis_row.source_metadata["output_tokens"] == 45
    assert analysis_row.source_metadata["total_tokens"] == 165
    assert analysis_row.source_metadata["score_breakdown"]["technical_maturity_score"] >= 0


def test_analyst_job_returns_skipped_paused_when_agent_is_paused(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(analyst_job_module, "is_agent_paused", lambda *_args, **_kwargs: True)

    class Provider:
        def get_readme(self, *, owner_login: str, repository_name: str) -> RepositoryReadme:
            del owner_login, repository_name
            raise AssertionError("get_readme should not run while paused")

    with _make_session(tmp_path) as session:
        result = run_analyst_job(
            session=session,
            provider=Provider(),  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
        )

    assert result.status is AnalystRunStatus.SKIPPED_PAUSED
    assert result.outcomes == []


def test_analyst_job_stops_after_current_repository_when_pause_requested_mid_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider = StubGitHubProvider(
        {
            1001: RepositoryReadme(
                owner_login="octocat",
                repository_name="first-repo",
                content="# First\n\nWorkflow automation for support teams.",
                fetched_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                source_url="https://api.github.com/repos/octocat/first-repo/readme",
            ),
            1002: RepositoryReadme(
                owner_login="octocat",
                repository_name="second-repo",
                content="# Second\n\nCRM workflow automation.",
                fetched_at=datetime(2026, 3, 8, 12, 1, tzinfo=timezone.utc),
                source_url="https://api.github.com/repos/octocat/second-repo/readme",
            ),
        }
    )

    pause_checks = {"count": 0}

    def fake_is_paused(*_args, **_kwargs) -> bool:
        pause_checks["count"] += 1
        return pause_checks["count"] >= 3

    monkeypatch.setattr(analyst_job_module, "is_agent_paused", fake_is_paused)

    with _make_session(tmp_path) as session:
        session.add(_accepted_row(1001, "octocat/first-repo"))
        session.add(_accepted_row(1002, "octocat/second-repo"))
        session.commit()

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
            analysis_provider=StaticAnalysisProvider(
                '{"monetization_potential":"medium","pros":["Automation"],'
                '"cons":["Needs validation"],"missing_feature_signals":["Missing billing"]}'
            ),
        )
        first_row = session.get(RepositoryAnalysisResult, 1001)
        second_row = session.get(RepositoryAnalysisResult, 1002)

    assert result.status is AnalystRunStatus.SKIPPED_PAUSED
    assert len(result.outcomes) == 1
    assert result.outcomes[0].github_repository_id == 1001
    assert first_row is not None
    assert second_row is None


def test_analyst_job_records_llm_timeout_events_with_llm_provider_context(tmp_path: Path) -> None:
    provider = StubGitHubProvider(
        {
            808: RepositoryReadme(
                owner_login="octocat",
                repository_name="llm-timeout",
                content="# Product\n\nWorkflow automation with analytics.",
                fetched_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                source_url="https://api.github.com/repos/octocat/llm-timeout/readme",
            )
        }
    )

    with _make_session(tmp_path) as session:
        session.add(_accepted_row(808, "octocat/llm-timeout"))
        session.add(AgentRun(agent_name="analyst", status=AgentRunStatus.RUNNING))
        session.commit()
        run = session.exec(select(AgentRun)).one()

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
            analysis_provider=RaisingAnalysisProvider(TimeoutError("LLM timed out")),
            agent_run_id=run.id,
        )
        row = session.get(RepositoryIntake, 808)
        event = session.exec(
            select(SystemEvent).where(SystemEvent.event_type == "repository_analysis_failed")
        ).one()

    assert result.status is AnalystRunStatus.FAILED
    assert row is not None
    assert row.analysis_status is RepositoryAnalysisStatus.FAILED
    assert row.analysis_failure_code is RepositoryAnalysisFailureCode.TRANSPORT_ERROR
    assert event.upstream_provider == "llm"
    assert event.failure_classification.value == "retryable"
    assert event.affected_repository_id == 808


def test_analyst_job_records_llm_rate_limit_event_context(tmp_path: Path) -> None:
    provider = StubGitHubProvider(
        {
            909: RepositoryReadme(
                owner_login="octocat",
                repository_name="llm-ratelimit",
                content="# Product\n\nAnalytics for SaaS workflow teams.",
                fetched_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                source_url="https://api.github.com/repos/octocat/llm-ratelimit/readme",
            )
        }
    )

    with _make_session(tmp_path) as session:
        session.add(_accepted_row(909, "octocat/llm-ratelimit"))
        session.add(AgentRun(agent_name="analyst", status=AgentRunStatus.RUNNING))
        session.commit()
        run = session.exec(select(AgentRun)).one()

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
            analysis_provider=RaisingAnalysisProvider(
                FakeRateLimitError(
                    "429 rate limit from llm provider",
                    status_code=429,
                    retry_after_seconds=45,
                )
            ),
            agent_run_id=run.id,
        )
        row = session.get(RepositoryIntake, 909)
        event = session.exec(
            select(SystemEvent).where(SystemEvent.event_type == "repository_analysis_failed")
        ).one()

    assert result.status is AnalystRunStatus.FAILED
    assert row is not None
    assert row.analysis_failure_code is RepositoryAnalysisFailureCode.RATE_LIMITED
    assert event.upstream_provider == "llm"
    assert event.failure_classification.value == "rate_limited"
    assert event.http_status_code == 429
    assert event.retry_after_seconds == 45


def test_analyst_github_rate_limit_does_not_pause_analyst(tmp_path: Path) -> None:
    """A GitHub rate limit while fetching READMEs must NOT pause analyst per AC2.

    GitHub rate limits pause firehose and backfill, but analyst is excluded because
    it processes already-fetched data paths. The pause policy must distinguish
    upstream_provider="github" from an LLM rate limit.
    """
    with _make_session(tmp_path) as session:
        session.add(_accepted_row(1001, "octocat/github-rl-repo"))
        session.add(_accepted_row(1002, "octocat/github-rl-next"))
        session.add(AgentRun(agent_name="analyst", status=AgentRunStatus.RUNNING))
        session.commit()
        run = session.exec(select(AgentRun)).one()

        provider = StubGitHubProvider(
            {1001: GitHubRateLimitError(status_code=429, retry_after_seconds=60)}
        )

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
            agent_run_id=run.id,
        )
        first_row = session.get(RepositoryIntake, 1001)
        second_row = session.get(RepositoryIntake, 1002)
        pause_state = session.exec(
            select(AgentPauseState).where(AgentPauseState.agent_name == "analyst")
        ).first()

    assert result.status is AnalystRunStatus.FAILED
    # The critical assertion: analyst must NOT be paused by a GitHub rate limit
    assert pause_state is None
    assert provider.calls == [("octocat", "github-rl-repo")]
    assert first_row is not None
    assert first_row.analysis_status is RepositoryAnalysisStatus.PENDING
    assert first_row.analysis_failure_code is RepositoryAnalysisFailureCode.RATE_LIMITED
    assert second_row is not None
    assert second_row.analysis_status is RepositoryAnalysisStatus.PENDING


def test_analyst_three_consecutive_retryable_failures_trigger_pause(tmp_path: Path) -> None:
    """3+ consecutive retryable failures from analyst must trigger an auto-pause.

    The consecutive_failures counter must be passed through to evaluate_pause_policy
    so the 3+ retryable rule is actually evaluated.
    """
    with _make_session(tmp_path) as session:
        for repo_id in (2001, 2002, 2003):
            session.add(_accepted_row(repo_id, f"octocat/repo-{repo_id}"))
        session.add(AgentRun(agent_name="analyst", status=AgentRunStatus.RUNNING))
        session.commit()
        run = session.exec(select(AgentRun)).one()

        # Stub: every repo fetch raises a generic GitHubProviderError (→ RETRYABLE)
        provider = StubGitHubProvider(
            {2001: GitHubProviderError("connection reset")}
        )

        result = run_analyst_job(
            session=session,
            provider=provider,  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
            agent_run_id=run.id,
        )
        pause_state = session.exec(
            select(AgentPauseState).where(AgentPauseState.agent_name == "analyst")
        ).first()

    assert result.status is AnalystRunStatus.FAILED
    # After 3 consecutive retryable failures analyst must be paused
    assert pause_state is not None
    assert pause_state.is_paused is True


def test_analyst_persists_failure_state_when_event_emission_rolls_back(tmp_path: Path, monkeypatch) -> None:
    with _make_session(tmp_path) as session:
        session.add(_accepted_row(3001, "octocat/event-sink-failure"))
        session.commit()

        monkeypatch.setattr(
            "agentic_workers.jobs.analyst_job.emit_failure_event",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("event sink failed")),
        )

        result = run_analyst_job(
            session=session,
            provider=StubGitHubProvider(
                {
                    3001: RepositoryReadme(
                        owner_login="octocat",
                        repository_name="event-sink-failure",
                        content="# Product\n\nWorkflow automation with analytics.",
                        fetched_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                        source_url="https://api.github.com/repos/octocat/event-sink-failure/readme",
                    )
                }
            ),  # type: ignore[arg-type]
            runtime_dir=tmp_path / "runtime",
            analysis_provider=RaisingAnalysisProvider(TimeoutError("LLM timed out")),
        )
        row = session.get(RepositoryIntake, 3001)
        events = session.exec(select(SystemEvent)).all()

    assert result.status is AnalystRunStatus.FAILED
    assert row is not None
    assert row.analysis_status is RepositoryAnalysisStatus.FAILED
    assert row.analysis_failure_code is RepositoryAnalysisFailureCode.TRANSPORT_ERROR
    assert events == []

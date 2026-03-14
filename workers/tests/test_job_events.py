from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, create_engine, select

from agentic_workers import main
from agentic_workers.providers.github_provider import (
    DiscoveredRepository,
    FirehoseMode,
    GitHubProviderError,
    GitHubRateLimitError,
    GitHubReadmeNotFoundError,
)
from agentic_workers.storage.backend_models import (
    AgentPauseState,
    AgentRun,
    AgentRunStatus,
    RepositoryAnalysisStatus,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
    SQLModel,
    SystemEvent,
)


class StubFirehoseProvider:
    def __init__(self, *, github_token: str | None) -> None:
        self.github_token = github_token

    def discover(
        self,
        *,
        mode: FirehoseMode,
        anchor_date: object = None,
        per_page: int = 25,
        page: int = 1,
    ) -> list[DiscoveredRepository]:
        del anchor_date, per_page, page
        repository_id = 101 if mode is FirehoseMode.NEW else 202
        return [
            DiscoveredRepository(
                github_repository_id=repository_id,
                owner_login="octocat",
                repository_name=f"repo-{repository_id}",
                full_name=f"octocat/repo-{repository_id}",
                created_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
                firehose_discovery_mode=mode,
            )
        ]


class StubAnalystProvider:
    def __init__(self, *, github_token: str | None) -> None:
        self.github_token = github_token

    def get_readme(self, *, owner_login: str, repository_name: str) -> None:
        raise GitHubReadmeNotFoundError(
            f"Repository README not found for {owner_login}/{repository_name}"
        )


class StubBackfillProvider:
    def __init__(self, *, github_token: str | None) -> None:
        self.github_token = github_token

    def discover_backfill(self, **_: object) -> list[DiscoveredRepository]:
        return []


class RateLimitedBackfillProvider:
    def __init__(self, *, github_token: str | None) -> None:
        self.github_token = github_token

    def discover_backfill(self, **_: object) -> list[DiscoveredRepository]:
        raise GitHubRateLimitError(status_code=403, retry_after_seconds=17)


class RateLimitedFirehoseProvider:
    def __init__(self, *, github_token: str | None) -> None:
        self.github_token = github_token

    def discover(
        self,
        *,
        mode: FirehoseMode,
        anchor_date: object = None,
        per_page: int = 25,
        page: int = 1,
    ) -> list[DiscoveredRepository]:
        del mode, anchor_date, per_page, page
        raise GitHubRateLimitError(status_code=403, retry_after_seconds=13)


class FailingFirehoseProvider:
    def __init__(self, *, github_token: str | None) -> None:
        self.github_token = github_token

    def discover(
        self,
        *,
        mode: FirehoseMode,
        anchor_date: object = None,
        per_page: int = 25,
        page: int = 1,
    ) -> list[DiscoveredRepository]:
        del mode, anchor_date, per_page, page
        raise GitHubProviderError("github transport failed")


class FailingBackfillProvider:
    def __init__(self, *, github_token: str | None) -> None:
        self.github_token = github_token

    def discover_backfill(self, **_: object) -> list[DiscoveredRepository]:
        raise GitHubProviderError("github transport failed")


def _make_engine(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'job-events.db'}")
    SQLModel.metadata.create_all(engine)
    return engine


def test_run_configured_firehose_job_persists_agent_run_and_events(
    monkeypatch,
    tmp_path: Path,
) -> None:
    engine = _make_engine(tmp_path)

    class StubSettings:
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path / "runtime"

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 1
            firehose_per_page = 100
            firehose_pages = 1
            firehose_interval_seconds = 60
            backfill_per_page = 50
            backfill_pages = 1
            backfill_window_days = 30
            backfill_min_created_date = "2008-01-01"
            backfill_interval_seconds = 60

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "GitHubFirehoseProvider", StubFirehoseProvider)

    result = main.run_configured_firehose_job(sleep_fn=lambda _seconds: None)

    with Session(engine) as session:
        runs = session.exec(select(AgentRun).order_by(AgentRun.id)).all()
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert result.status.value == "success"
    assert len(runs) == 1
    assert runs[0].status is AgentRunStatus.COMPLETED
    assert runs[0].items_processed == 2
    assert runs[0].items_succeeded == 2
    assert runs[0].items_failed == 0
    assert [event.event_type for event in events] == ["agent_started", "agent_completed"]


def test_run_configured_firehose_job_records_rate_limit_events(
    monkeypatch,
    tmp_path: Path,
) -> None:
    engine = _make_engine(tmp_path)

    class StubSettings:
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path / "runtime"

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 1
            firehose_per_page = 100
            firehose_pages = 1
            firehose_interval_seconds = 60
            backfill_per_page = 50
            backfill_pages = 1
            backfill_window_days = 30
            backfill_min_created_date = "2008-01-01"
            backfill_interval_seconds = 60

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "GitHubFirehoseProvider", RateLimitedFirehoseProvider)

    result = main.run_configured_firehose_job(sleep_fn=lambda _seconds: None)

    with Session(engine) as session:
        run = session.exec(select(AgentRun)).one()
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()
        firehose_run_events = session.exec(
            select(SystemEvent)
            .where(SystemEvent.agent_run_id == run.id)
            .order_by(SystemEvent.id)
        ).all()

    assert result.status.value == "failed"
    assert run.status is AgentRunStatus.FAILED
    assert [event.event_type for event in events] == [
        "agent_started",
        "rate_limit_hit",
        "agent_paused",
        "agent_paused",
        "agent_failed",
    ]
    assert [(event.agent_name, event.agent_run_id) for event in events] == [
        ("firehose", run.id),
        ("firehose", run.id),
        ("firehose", run.id),
        ("backfill", None),
        ("firehose", run.id),
    ]
    assert [event.agent_name for event in firehose_run_events] == [
        "firehose",
        "firehose",
        "firehose",
        "firehose",
    ]


def test_run_configured_firehose_job_records_non_rate_limit_github_failures(
    monkeypatch,
    tmp_path: Path,
) -> None:
    engine = _make_engine(tmp_path)

    class StubSettings:
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path / "runtime"

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 1
            firehose_per_page = 100
            firehose_pages = 1
            firehose_interval_seconds = 60
            backfill_per_page = 50
            backfill_pages = 1
            backfill_window_days = 30
            backfill_min_created_date = "2008-01-01"
            backfill_interval_seconds = 60

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "GitHubFirehoseProvider", FailingFirehoseProvider)

    result = main.run_configured_firehose_job(sleep_fn=lambda _seconds: None)

    with Session(engine) as session:
        run = session.exec(select(AgentRun)).one()
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert result.status.value == "failed"
    assert run.status is AgentRunStatus.FAILED
    assert [event.event_type for event in events] == [
        "agent_started",
        "repository_discovery_failed",
        "agent_failed",
    ]


def test_run_configured_firehose_job_marks_immediate_shutdown_as_skipped(
    monkeypatch,
    tmp_path: Path,
) -> None:
    engine = _make_engine(tmp_path)

    class StubSettings:
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path / "runtime"

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 1
            firehose_per_page = 100
            firehose_pages = 1
            firehose_interval_seconds = 60
            backfill_per_page = 50
            backfill_pages = 1
            backfill_window_days = 30
            backfill_min_created_date = "2008-01-01"
            backfill_interval_seconds = 60

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "GitHubFirehoseProvider", StubFirehoseProvider)

    result = main.run_configured_firehose_job(
        sleep_fn=lambda _seconds: None,
        should_stop=lambda: True,
    )

    with Session(engine) as session:
        run = session.exec(select(AgentRun)).one()
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert result.status.value == "skipped"
    assert run.status is AgentRunStatus.SKIPPED
    assert run.items_processed == 0
    assert run.items_succeeded == 0
    assert run.items_failed == 0
    assert [event.event_type for event in events] == ["agent_started", "agent_skipped"]


def test_run_configured_firehose_job_marks_partial_shutdown_as_skipped(
    monkeypatch,
    tmp_path: Path,
) -> None:
    engine = _make_engine(tmp_path)

    class StubSettings:
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path / "runtime"

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 1
            firehose_per_page = 100
            firehose_pages = 2
            firehose_interval_seconds = 60
            backfill_per_page = 50
            backfill_pages = 1
            backfill_window_days = 30
            backfill_min_created_date = "2008-01-01"
            backfill_interval_seconds = 60

    stop_calls = 0

    def should_stop() -> bool:
        nonlocal stop_calls
        stop_calls += 1
        return stop_calls >= 2

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "GitHubFirehoseProvider", StubFirehoseProvider)

    result = main.run_configured_firehose_job(
        sleep_fn=lambda _seconds: None,
        should_stop=should_stop,
    )

    with Session(engine) as session:
        run = session.exec(select(AgentRun)).one()
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert result.status.value == "skipped"
    assert run.status is AgentRunStatus.SKIPPED
    assert run.items_processed == 1
    assert run.items_succeeded == 1
    assert run.items_failed == 0
    assert [event.event_type for event in events] == ["agent_started", "agent_skipped"]


def test_run_configured_firehose_job_persists_paused_skip_status(
    monkeypatch,
    tmp_path: Path,
) -> None:
    engine = _make_engine(tmp_path)

    class StubSettings:
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path / "runtime"

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 1
            firehose_per_page = 100
            firehose_pages = 1
            firehose_interval_seconds = 60
            backfill_per_page = 50
            backfill_pages = 1
            backfill_window_days = 30
            backfill_min_created_date = "2008-01-01"
            backfill_interval_seconds = 60

    with Session(engine) as session:
        session.add(
            AgentPauseState(
                agent_name="firehose",
                is_paused=True,
                pause_reason="GitHub rate limit",
            )
        )
        session.commit()

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "GitHubFirehoseProvider", StubFirehoseProvider)

    result = main.run_configured_firehose_job(sleep_fn=lambda _seconds: None)

    with Session(engine) as session:
        run = session.exec(select(AgentRun)).one()
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert result.status.value == "skipped_paused"
    assert run.status is AgentRunStatus.SKIPPED_PAUSED
    assert run.error_summary == "firehose paused by policy."
    assert [event.event_type for event in events] == ["agent_started", "agent_skipped_paused"]


def test_run_configured_analyst_job_records_failed_run_and_error_events(
    monkeypatch,
    tmp_path: Path,
) -> None:
    engine = _make_engine(tmp_path)

    class StubSettings:
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path / "runtime"

    with Session(engine) as session:
        session.add(
            RepositoryIntake(
                github_repository_id=303,
                owner_login="octocat",
                repository_name="missing-readme",
                full_name="octocat/missing-readme",
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.PENDING,
                discovered_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
                queue_created_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
                status_updated_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
                triaged_at=datetime(2026, 3, 10, 12, 1, tzinfo=timezone.utc),
            )
        )
        session.commit()

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "GitHubFirehoseProvider", StubAnalystProvider)
    monkeypatch.setattr(main, "HeuristicReadmeAnalysisProvider", lambda: object())

    result = main.run_configured_analyst_job()

    with Session(engine) as session:
        run = session.exec(select(AgentRun)).one()
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert result.status.value == "failed"
    assert run.status is AgentRunStatus.FAILED
    assert run.items_processed == 1
    assert run.items_failed == 1
    assert [event.event_type for event in events] == [
        "agent_started",
        "repository_analysis_failed",
        "agent_paused",
        "agent_failed",
    ]


def test_run_configured_backfill_job_persists_window_exhausted_event(
    monkeypatch,
    tmp_path: Path,
) -> None:
    engine = _make_engine(tmp_path)

    class StubSettings:
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path / "runtime"

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 1
            firehose_per_page = 100
            firehose_pages = 1
            firehose_interval_seconds = 60
            backfill_per_page = 50
            backfill_pages = 1
            backfill_window_days = 1
            backfill_min_created_date = datetime(2026, 3, 10, tzinfo=timezone.utc).date()
            backfill_interval_seconds = 60

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "GitHubFirehoseProvider", StubBackfillProvider)

    result = main.run_configured_backfill_job(sleep_fn=lambda _seconds: None)

    with Session(engine) as session:
        runs = session.exec(select(AgentRun).order_by(AgentRun.id)).all()
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert result.status.value == "success"
    assert len(runs) == 1
    assert runs[0].status is AgentRunStatus.COMPLETED
    assert [event.event_type for event in events] == [
        "agent_started",
        "window_exhausted",
        "agent_completed",
    ]


def test_run_configured_backfill_job_records_rate_limit_events(
    monkeypatch,
    tmp_path: Path,
) -> None:
    engine = _make_engine(tmp_path)

    class StubSettings:
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path / "runtime"

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 1
            firehose_per_page = 100
            firehose_pages = 1
            firehose_interval_seconds = 60
            backfill_per_page = 50
            backfill_pages = 1
            backfill_window_days = 1
            backfill_min_created_date = datetime(2026, 3, 9, tzinfo=timezone.utc).date()
            backfill_interval_seconds = 60

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "GitHubFirehoseProvider", RateLimitedBackfillProvider)

    result = main.run_configured_backfill_job(sleep_fn=lambda _seconds: None)

    with Session(engine) as session:
        run = session.exec(select(AgentRun)).one()
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()
        backfill_run_events = session.exec(
            select(SystemEvent)
            .where(SystemEvent.agent_run_id == run.id)
            .order_by(SystemEvent.id)
        ).all()

    assert result.status.value == "failed"
    assert run.status is AgentRunStatus.FAILED
    assert [event.event_type for event in events] == [
        "agent_started",
        "rate_limit_hit",
        "agent_paused",
        "agent_paused",
        "agent_failed",
    ]
    assert [(event.agent_name, event.agent_run_id) for event in events] == [
        ("backfill", run.id),
        ("backfill", run.id),
        ("firehose", None),
        ("backfill", run.id),
        ("backfill", run.id),
    ]
    assert [event.agent_name for event in backfill_run_events] == [
        "backfill",
        "backfill",
        "backfill",
        "backfill",
    ]


def test_run_configured_backfill_job_records_non_rate_limit_github_failures(
    monkeypatch,
    tmp_path: Path,
) -> None:
    engine = _make_engine(tmp_path)

    class StubSettings:
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path / "runtime"

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 1
            firehose_per_page = 100
            firehose_pages = 1
            firehose_interval_seconds = 60
            backfill_per_page = 50
            backfill_pages = 1
            backfill_window_days = 1
            backfill_min_created_date = datetime(2026, 3, 9, tzinfo=timezone.utc).date()
            backfill_interval_seconds = 60

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "GitHubFirehoseProvider", FailingBackfillProvider)

    result = main.run_configured_backfill_job(sleep_fn=lambda _seconds: None)

    with Session(engine) as session:
        run = session.exec(select(AgentRun)).one()
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert result.status.value == "failed"
    assert run.status is AgentRunStatus.FAILED
    assert [event.event_type for event in events] == [
        "agent_started",
        "repository_discovery_failed",
        "agent_failed",
    ]


def test_run_configured_bouncer_job_persists_agent_run_and_events(
    monkeypatch,
    tmp_path: Path,
) -> None:
    engine = _make_engine(tmp_path)

    class StubSettings:
        class runtime:
            runtime_dir = tmp_path / "runtime"

        class provider:
            bouncer_include_rules = ()
            bouncer_exclude_rules = ()

    with Session(engine) as session:
        session.add(
            RepositoryIntake(
                github_repository_id=404,
                owner_login="octocat",
                repository_name="bouncer-target",
                full_name="octocat/bouncer-target",
                queue_status=RepositoryQueueStatus.PENDING,
                triage_status=RepositoryTriageStatus.PENDING,
                analysis_status=RepositoryAnalysisStatus.PENDING,
                discovered_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
                queue_created_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
                status_updated_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
            )
        )
        session.commit()

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "engine", engine)

    result = main.run_configured_bouncer_job()

    with Session(engine) as session:
        run = session.exec(select(AgentRun)).one()
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert result.status.value == "success"
    assert run.status is AgentRunStatus.COMPLETED
    assert run.items_processed == 1
    assert run.items_succeeded == 1
    assert [event.event_type for event in events] == ["agent_started", "agent_completed"]


def test_run_configured_bouncer_job_records_failure_events(
    monkeypatch,
    tmp_path: Path,
) -> None:
    engine = _make_engine(tmp_path)

    class StubSettings:
        class runtime:
            runtime_dir = tmp_path / "runtime"

        class provider:
            bouncer_include_rules = ()
            bouncer_exclude_rules = ()

    with Session(engine) as session:
        session.add(
            RepositoryIntake(
                github_repository_id=505,
                owner_login="octocat",
                repository_name="broken-bouncer",
                full_name="octocat/broken-bouncer",
                queue_status=RepositoryQueueStatus.PENDING,
                triage_status=RepositoryTriageStatus.PENDING,
                analysis_status=RepositoryAnalysisStatus.PENDING,
                discovered_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
                queue_created_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
                status_updated_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
            )
        )
        session.commit()

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(
        "agentic_workers.jobs.bouncer_job.evaluate_repository",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("rule evaluation exploded")),
    )

    result = main.run_configured_bouncer_job()

    with Session(engine) as session:
        run = session.exec(select(AgentRun)).one()
        events = session.exec(select(SystemEvent).order_by(SystemEvent.id)).all()

    assert result.status.value == "failed"
    assert run.status is AgentRunStatus.FAILED
    assert [event.event_type for event in events] == [
        "agent_started",
        "repository_triage_failed",
        "agent_paused",
        "agent_failed",
    ]

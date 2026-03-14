from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from agentic_workers.jobs.analyst_job import (
    AnalystRepositoryOutcome,
    AnalystRunResult,
    AnalystRunStatus,
)
from agentic_workers.jobs.backfill_job import (
    BackfillPageOutcome,
    BackfillRunResult,
    BackfillRunStatus,
)
from agentic_workers.jobs.bouncer_job import (
    BouncerRepositoryOutcome,
    BouncerRunResult,
    BouncerRunStatus,
)
from agentic_workers.jobs.firehose_job import (
    FirehosePageOutcome,
    FirehoseRunResult,
    FirehoseRunStatus,
)
from agentic_workers.providers.github_provider import FirehoseMode
from agentic_workers.storage.backfill_progress import BackfillCheckpointState
from agentic_workers.storage.backend_models import (
    RepositoryAnalysisStatus,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
)
from agentic_workers.storage.firehose_progress import FirehoseCheckpointState
from agentic_workers import main


class DummyProvider:
    def __init__(self, *, github_token: str | None) -> None:
        self.github_token = github_token


class DummySession:
    def __init__(self, engine: object) -> None:
        self.engine = engine

    def __enter__(self) -> "DummySession":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def rollback(self) -> None:
        return None


def test_configured_firehose_job_uses_settings_and_runtime_paths(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class StubSettings:
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 3
            firehose_per_page = 100
            firehose_pages = 1
            backfill_per_page = 50
            backfill_pages = 2
            backfill_window_days = 30
            backfill_min_created_date = "2008-01-01"
            backfill_interval_seconds = 3600

    def fake_run_firehose_job(**kwargs: object) -> FirehoseRunResult:
        captured.update(kwargs)
        return FirehoseRunResult(
            status=FirehoseRunStatus.SUCCESS,
            outcomes=[],
            artifact_path=None,
            artifact_error=None,
        )

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "GitHubFirehoseProvider", DummyProvider)
    monkeypatch.setattr(main, "Session", DummySession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "run_firehose_job", fake_run_firehose_job)
    monkeypatch.setattr(main, "start_agent_run", lambda session, agent_name: 11)
    monkeypatch.setattr(
        main,
        "finalize_agent_run",
        lambda session, run_id, items_processed, items_succeeded, items_failed: None,
    )
    monkeypatch.setattr(
        main,
        "record_failed_agent_run",
        lambda session, run_id, error_summary, error_context, items_processed, items_succeeded, items_failed: None,
    )

    result = main.run_configured_firehose_job()

    assert result.status is FirehoseRunStatus.SUCCESS
    assert isinstance(captured["provider"], DummyProvider)
    assert captured["provider"].github_token == "worker-token"
    assert captured["runtime_dir"] == tmp_path
    assert captured["pacing_seconds"] == 3
    assert captured["modes"] == (FirehoseMode.NEW, FirehoseMode.TRENDING)
    assert captured["agent_run_id"] == 11


def test_configured_backfill_job_uses_settings_and_runtime_paths(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class StubSettings:
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 3
            firehose_per_page = 100
            firehose_pages = 1
            backfill_per_page = 25
            backfill_pages = 2
            backfill_window_days = 14
            backfill_min_created_date = "2015-01-01"
            backfill_interval_seconds = 7200

    def fake_run_backfill_job(**kwargs: object) -> BackfillRunResult:
        captured.update(kwargs)
        return BackfillRunResult(
            status=BackfillRunStatus.SUCCESS,
            outcomes=[],
            checkpoint=type("Checkpoint", (), {"exhausted": False})(),
            artifact_path=None,
            artifact_error=None,
        )

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "GitHubFirehoseProvider", DummyProvider)
    monkeypatch.setattr(main, "Session", DummySession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "run_backfill_job", fake_run_backfill_job)
    monkeypatch.setattr(main, "start_agent_run", lambda session, agent_name: 22)
    monkeypatch.setattr(
        main,
        "finalize_agent_run",
        lambda session, run_id, items_processed, items_succeeded, items_failed: None,
    )
    monkeypatch.setattr(
        main,
        "record_failed_agent_run",
        lambda session, run_id, error_summary, error_context, items_processed, items_succeeded, items_failed: None,
    )

    result = main.run_configured_backfill_job()

    assert result.status is BackfillRunStatus.SUCCESS
    assert isinstance(captured["provider"], DummyProvider)
    assert captured["provider"].github_token == "worker-token"
    assert captured["runtime_dir"] == tmp_path
    assert captured["pacing_seconds"] == 3
    assert captured["per_page"] == 25
    assert captured["pages"] == 2
    assert captured["window_days"] == 14
    assert captured["min_created_date"] == "2015-01-01"
    assert captured["agent_run_id"] == 22


def test_configured_bouncer_job_uses_settings_and_runtime_paths(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class StubSettings:
        class runtime:
            runtime_dir = tmp_path

        class provider:
            bouncer_include_rules = ("saas", "developer tools")
            bouncer_exclude_rules = ("gaming", "tutorial")

    def fake_run_bouncer_job(**kwargs: object) -> BouncerRunResult:
        captured.update(kwargs)
        return BouncerRunResult(
            status=BouncerRunStatus.SUCCESS,
            outcomes=[],
            artifact_path=None,
            artifact_error=None,
        )

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "Session", DummySession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "run_bouncer_job", fake_run_bouncer_job)
    monkeypatch.setattr(main, "start_agent_run", lambda session, agent_name: 33)
    monkeypatch.setattr(
        main,
        "finalize_agent_run",
        lambda session, run_id, items_processed, items_succeeded, items_failed: None,
    )
    monkeypatch.setattr(
        main,
        "record_failed_agent_run",
        lambda session, run_id, error_summary, error_context, items_processed, items_succeeded, items_failed: None,
    )

    result = main.run_configured_bouncer_job()

    assert result.status is BouncerRunStatus.SUCCESS
    assert captured["runtime_dir"] == tmp_path
    assert captured["include_rules"] == ("saas", "developer tools")
    assert captured["exclude_rules"] == ("gaming", "tutorial")
    assert captured["agent_run_id"] == 33


def test_configured_analyst_job_uses_settings_and_runtime_paths(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class StubSettings:
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path

    def fake_run_analyst_job(**kwargs: object) -> AnalystRunResult:
        captured.update(kwargs)
        return AnalystRunResult(
            status=AnalystRunStatus.SUCCESS,
            outcomes=[],
            artifact_path=None,
            artifact_error=None,
        )

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "GitHubFirehoseProvider", DummyProvider)
    monkeypatch.setattr(main, "HeuristicReadmeAnalysisProvider", lambda: "heuristic-provider")
    monkeypatch.setattr(main, "Session", DummySession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "run_analyst_job", fake_run_analyst_job)
    monkeypatch.setattr(main, "start_agent_run", lambda session, agent_name: 44)
    monkeypatch.setattr(
        main,
        "finalize_agent_run",
        lambda session, run_id, items_processed, items_succeeded, items_failed: None,
    )
    monkeypatch.setattr(
        main,
        "record_failed_agent_run",
        lambda session, run_id, error_summary, error_context, items_processed, items_succeeded, items_failed: None,
    )

    result = main.run_configured_analyst_job()

    assert result.status is AnalystRunStatus.SUCCESS
    assert isinstance(captured["provider"], DummyProvider)
    assert captured["provider"].github_token == "worker-token"
    assert captured["runtime_dir"] == tmp_path
    assert captured["analysis_provider"] == "heuristic-provider"
    assert captured["agent_run_id"] == 44


def test_configured_firehose_job_records_terminal_write_failures_as_failed_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    recorded_failure: dict[str, object | None] = {}

    class StubSettings:
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 3
            firehose_per_page = 100
            firehose_pages = 1
            backfill_per_page = 50
            backfill_pages = 2
            backfill_window_days = 30
            backfill_min_created_date = "2008-01-01"
            backfill_interval_seconds = 3600

    def fake_run_firehose_job(**_: object) -> FirehoseRunResult:
        return FirehoseRunResult(
            status=FirehoseRunStatus.SUCCESS,
            outcomes=[],
            artifact_path=None,
            artifact_error=None,
        )

    def failing_finalize(
        session: object,
        run_id: int,
        items_processed: int,
        items_succeeded: int,
        items_failed: int,
    ) -> None:
        del session, run_id, items_processed, items_succeeded, items_failed
        raise RuntimeError("cannot persist terminal state")

    def capture_failed_run(
        session: object,
        run_id: int,
        error_summary: str,
        error_context: str | None,
        items_processed: int | None,
        items_succeeded: int | None,
        items_failed: int | None,
    ) -> None:
        del session
        recorded_failure.update(
            {
                "run_id": run_id,
                "error_summary": error_summary,
                "error_context": error_context,
                "items_processed": items_processed,
                "items_succeeded": items_succeeded,
                "items_failed": items_failed,
            }
        )

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "GitHubFirehoseProvider", DummyProvider)
    monkeypatch.setattr(main, "Session", DummySession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "run_firehose_job", fake_run_firehose_job)
    monkeypatch.setattr(main, "start_agent_run", lambda session, agent_name: 51)
    monkeypatch.setattr(main, "finalize_agent_run", failing_finalize)
    monkeypatch.setattr(main, "record_failed_agent_run", capture_failed_run)

    with pytest.raises(RuntimeError, match="cannot persist terminal state"):
        main.run_configured_firehose_job()

    assert recorded_failure["run_id"] == 51
    assert recorded_failure["items_processed"] == 0
    assert recorded_failure["items_succeeded"] == 0
    assert recorded_failure["items_failed"] == 0
    assert recorded_failure["error_summary"] == (
        "firehose run crashed while persisting terminal state: cannot persist terminal state"
    )


def test_interrupted_empty_job_runs_are_marked_skipped() -> None:
    from agentic_workers.jobs import analyst_job, backfill_job, bouncer_job, firehose_job

    assert firehose_job._determine_status([], interrupted=True) is FirehoseRunStatus.SKIPPED
    assert backfill_job._determine_status([], interrupted=True) is BackfillRunStatus.SKIPPED
    assert bouncer_job._determine_status([], interrupted=True) is BouncerRunStatus.SKIPPED
    assert analyst_job._determine_status([], interrupted=True) is AnalystRunStatus.SKIPPED


def test_interrupted_runs_with_progress_are_marked_skipped() -> None:
    from agentic_workers.jobs import analyst_job, backfill_job, bouncer_job, firehose_job

    firehose_outcomes = [
        FirehosePageOutcome(
            mode=FirehoseMode.NEW,
            page=1,
            anchor_date=date(2026, 3, 10),
            fetched_count=1,
            inserted_count=1,
            skipped_count=0,
        )
    ]
    backfill_outcomes = [
        BackfillPageOutcome(
            window_start_date=date(2026, 3, 1),
            created_before_boundary=date(2026, 3, 10),
            created_before_cursor=None,
            page=1,
            fetched_count=1,
            inserted_count=1,
            skipped_count=0,
            exhausted_after=False,
        )
    ]
    bouncer_outcomes = [
        BouncerRepositoryOutcome(
            github_repository_id=1,
            full_name="octocat/repo",
            triage_status=RepositoryTriageStatus.ACCEPTED,
            queue_status=RepositoryQueueStatus.COMPLETED,
            explanation_kind=None,
            explanation_summary=None,
            explained_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
            matched_include_rules=(),
            matched_exclude_rules=(),
        )
    ]
    analyst_outcomes = [
        AnalystRepositoryOutcome(
            github_repository_id=1,
            full_name="octocat/repo",
            analysis_status=RepositoryAnalysisStatus.COMPLETED,
            failure_code=None,
            failure_message=None,
            monetization_potential="medium",
            runtime_readme_artifact_path="runtime/readme.md",
            runtime_analysis_artifact_path="runtime/analysis.json",
        )
    ]

    assert (
        firehose_job._determine_status(firehose_outcomes, interrupted=True)
        is FirehoseRunStatus.SKIPPED
    )
    assert (
        backfill_job._determine_status(backfill_outcomes, interrupted=True)
        is BackfillRunStatus.SKIPPED
    )
    assert (
        bouncer_job._determine_status(bouncer_outcomes, interrupted=True)
        is BouncerRunStatus.SKIPPED
    )
    assert (
        analyst_job._determine_status(analyst_outcomes, interrupted=True)
        is AnalystRunStatus.SKIPPED
    )


def test_firehose_pacing_respects_request_budget_floor(monkeypatch) -> None:
    class StubSettings:
        class provider:
            github_requests_per_minute = 20
            intake_pacing_seconds = 1
            firehose_pages = 2
            backfill_pages = 2

    monkeypatch.setattr(main, "settings", StubSettings())

    assert main.calculate_firehose_pacing_seconds() == 3


def test_calculate_firehose_interval_clamps_to_request_budget(monkeypatch) -> None:
    """Firehose interval is clamped against the combined Firehose + Backfill request budget."""

    class StubSettings:
        class provider:
            github_requests_per_minute = 20  # pacing = ceil(60/20) = 3s
            intake_pacing_seconds = 1  # lower than budget floor — floor wins
            firehose_interval_seconds = 1  # too small for (2 firehose modes × 2 pages + 1 backfill page) × 3s
            firehose_pages = 2
            backfill_pages = 1
            backfill_interval_seconds = 1

    monkeypatch.setattr(main, "settings", StubSettings())
    # (4 firehose requests + 1 backfill request) × 3s pacing = 15s minimum.
    assert main.calculate_firehose_interval_seconds() == 15


def test_calculate_backfill_interval_clamps_to_shared_request_budget(monkeypatch) -> None:
    class StubSettings:
        class provider:
            github_requests_per_minute = 20
            intake_pacing_seconds = 1
            firehose_interval_seconds = 3600
            firehose_pages = 2
            backfill_interval_seconds = 1
            backfill_pages = 2

    monkeypatch.setattr(main, "settings", StubSettings())

    # (4 firehose requests + 2 backfill requests) × 3s pacing = 18s minimum.
    assert main.calculate_backfill_interval_seconds() == 18


def test_calculate_backfill_interval_rejects_non_positive_config(monkeypatch) -> None:
    class StubSettings:
        class provider:
            github_requests_per_minute = 20
            intake_pacing_seconds = 1
            firehose_interval_seconds = 3600
            firehose_pages = 2
            backfill_interval_seconds = 0
            backfill_pages = 2

    monkeypatch.setattr(main, "settings", StubSettings())

    with pytest.raises(ValueError, match="backfill_interval_seconds must be greater than zero"):
        main.calculate_backfill_interval_seconds()


def test_has_pending_analyst_work_queries_for_accepted_repositories(monkeypatch) -> None:
    class StubResult:
        def one(self) -> int:
            return 2

    class StubSession:
        def __init__(self, engine: object) -> None:
            self.engine = engine

        def __enter__(self) -> "StubSession":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def exec(self, _statement: object) -> StubResult:
            return StubResult()

    monkeypatch.setattr(main, "Session", StubSession)
    monkeypatch.setattr(main, "engine", object())

    assert main.has_pending_analyst_work() is True


def test_should_run_backfill_startup_respects_last_checkpoint_time(monkeypatch) -> None:
    class StubSession:
        def __init__(self, engine: object) -> None:
            self.engine = engine

        def __enter__(self) -> "StubSession":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    recent_checkpoint = BackfillCheckpointState(
        source_provider="github",
        window_start_date=date(2026, 2, 1),
        created_before_boundary=date(2026, 3, 1),
        created_before_cursor=None,
        next_page=1,
        exhausted=False,
        last_checkpointed_at=datetime(2026, 3, 8, 11, 30, tzinfo=timezone.utc),
    )

    class StubSettings:
        class provider:
            github_requests_per_minute = 60
            intake_pacing_seconds = 30
            firehose_pages = 1
            firehose_interval_seconds = 3600
            backfill_pages = 1
            backfill_interval_seconds = 3600

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "Session", StubSession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "load_backfill_progress", lambda _session: recent_checkpoint)

    assert (
        main.should_run_backfill_startup(
            now=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc).timestamp()
        )
        is False
    )


def test_seconds_until_next_firehose_run_returns_zero_when_resume_is_pending(monkeypatch) -> None:
    class StubSession:
        def __init__(self, engine: object) -> None:
            self.engine = engine

        def __enter__(self) -> "StubSession":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    checkpoint = FirehoseCheckpointState(
        source_provider="github",
        active_mode=FirehoseMode.TRENDING,
        next_page=2,
        new_anchor_date=date(2026, 3, 7),
        trending_anchor_date=date(2026, 3, 1),
        run_started_at=datetime(2026, 3, 8, 11, 0, tzinfo=timezone.utc),
        resume_required=True,
        last_checkpointed_at=datetime(2026, 3, 8, 11, 30, tzinfo=timezone.utc),
    )

    monkeypatch.setattr(main, "Session", StubSession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "load_firehose_progress", lambda _session: checkpoint)

    assert main.seconds_until_next_firehose_run() == pytest.approx(0.0)


def test_seconds_until_next_firehose_run_returns_zero_on_fresh_install(monkeypatch) -> None:
    """Fresh database (no checkpoint) should return 0.0 so Firehose runs immediately."""

    class StubSession:
        def __init__(self, engine: object) -> None:
            self.engine = engine

        def __enter__(self) -> "StubSession":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    monkeypatch.setattr(main, "Session", StubSession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "load_firehose_progress", lambda _session: None)

    assert main.seconds_until_next_firehose_run() == pytest.approx(0.0)


def test_seconds_until_next_firehose_run_uses_interval_after_completed_run(monkeypatch) -> None:
    """After a completed run with recent checkpoint, the full interval should be respected."""

    class StubSession:
        def __init__(self, engine: object) -> None:
            self.engine = engine

        def __enter__(self) -> "StubSession":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    completed_checkpoint = FirehoseCheckpointState(
        source_provider="github",
        active_mode=None,
        next_page=1,
        new_anchor_date=None,
        trending_anchor_date=None,
        run_started_at=None,
        resume_required=False,
        last_checkpointed_at=datetime(2026, 3, 8, 11, 30, tzinfo=timezone.utc),
    )

    class StubSettings:
        class provider:
            github_requests_per_minute = 60
            intake_pacing_seconds = 30
            firehose_interval_seconds = 3600
            firehose_pages = 1
            backfill_pages = 1

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "Session", StubSession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "load_firehose_progress", lambda _session: completed_checkpoint)

    remaining = main.seconds_until_next_firehose_run(
        now=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc).timestamp()
    )
    assert remaining == pytest.approx(1800.0)


def test_seconds_until_next_backfill_run_returns_remaining_interval(monkeypatch) -> None:
    class StubSession:
        def __init__(self, engine: object) -> None:
            self.engine = engine

        def __enter__(self) -> "StubSession":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    recent_checkpoint = BackfillCheckpointState(
        source_provider="github",
        window_start_date=date(2026, 2, 1),
        created_before_boundary=date(2026, 3, 1),
        created_before_cursor=None,
        next_page=1,
        exhausted=False,
        last_checkpointed_at=datetime(2026, 3, 8, 11, 30, tzinfo=timezone.utc),
    )

    class StubSettings:
        class provider:
            github_requests_per_minute = 60
            intake_pacing_seconds = 30
            firehose_pages = 1
            firehose_interval_seconds = 3600
            backfill_pages = 1
            backfill_interval_seconds = 3600

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "Session", StubSession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "load_backfill_progress", lambda _session: recent_checkpoint)

    remaining = main.seconds_until_next_backfill_run(
        now=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc).timestamp()
    )

    assert remaining == pytest.approx(1800.0)


def test_seconds_until_next_backfill_run_returns_zero_on_fresh_install(monkeypatch) -> None:
    """Fresh database (no checkpoint) should return 0.0 so Backfill runs immediately."""

    class StubSession:
        def __init__(self, engine: object) -> None:
            self.engine = engine

        def __enter__(self) -> "StubSession":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    monkeypatch.setattr(main, "Session", StubSession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "load_backfill_progress", lambda _session: None)

    remaining = main.seconds_until_next_backfill_run(now=0.0)

    assert remaining == pytest.approx(0.0)


def test_main_skips_startup_backfill_until_interval_due(monkeypatch) -> None:
    run_calls: list[str] = []

    class StubSettings:
        github_provider_token_value = None

        class runtime:
            runtime_dir = None

        class provider:
            github_requests_per_minute = 60
            intake_pacing_seconds = 30
            firehose_interval_seconds = 3600
            firehose_per_page = 100
            firehose_pages = 1
            backfill_interval_seconds = 3600
            backfill_per_page = 100
            backfill_pages = 1
            backfill_window_days = 30
            backfill_min_created_date = "2008-01-01"

    success_firehose_result = FirehoseRunResult(
        status=FirehoseRunStatus.SUCCESS,
        outcomes=[],
        artifact_path=None,
        artifact_error=None,
    )

    _real_event_class = asyncio.Event
    stop_event_ref: list[asyncio.Event] = []

    class _CapturingEvent:
        def __init__(self) -> None:
            self._inner = _real_event_class()
            if not stop_event_ref:
                stop_event_ref.append(self._inner)

        def set(self) -> None:
            self._inner.set()

        def is_set(self) -> bool:
            return self._inner.is_set()

        async def wait(self) -> None:
            await self._inner.wait()

    async def fake_to_thread(func: object, *args: object, **kwargs: object) -> object:
        if func is main.run_configured_firehose_job:
            run_calls.append("firehose")
            if stop_event_ref:
                stop_event_ref[0].set()
            return success_firehose_result
        if func is main.run_configured_backfill_job:
            run_calls.append("backfill")
        return None

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "should_run_firehose_startup", lambda **kwargs: True)
    monkeypatch.setattr(main, "should_run_backfill_startup", lambda **kwargs: False)
    monkeypatch.setattr(main, "has_pending_bouncer_work", lambda: False)
    monkeypatch.setattr(main, "seconds_until_next_firehose_run", lambda now=None: 1800.0)
    monkeypatch.setattr(main, "seconds_until_next_backfill_run", lambda now=None: 1800.0)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "Event", _CapturingEvent)

    asyncio.run(main.main())

    assert run_calls == ["firehose"]


def test_main_logs_firehose_interval_gate_when_no_resume_is_pending(
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    run_calls: list[str] = []

    class StubSettings:
        github_provider_token_value = None

        class runtime:
            runtime_dir = None

        class provider:
            github_requests_per_minute = 60
            intake_pacing_seconds = 30
            firehose_interval_seconds = 1800
            firehose_per_page = 100
            firehose_pages = 1
            backfill_interval_seconds = 3600
            backfill_per_page = 100
            backfill_pages = 1
            backfill_window_days = 30
            backfill_min_created_date = "2008-01-01"

    success_firehose_result = FirehoseRunResult(
        status=FirehoseRunStatus.SUCCESS,
        outcomes=[],
        artifact_path=None,
        artifact_error=None,
    )

    _real_event_class = asyncio.Event
    stop_event_ref: list[asyncio.Event] = []

    class _CapturingEvent:
        def __init__(self) -> None:
            self._inner = _real_event_class()
            if not stop_event_ref:
                stop_event_ref.append(self._inner)

        def set(self) -> None:
            self._inner.set()

        def is_set(self) -> bool:
            return self._inner.is_set()

        async def wait(self) -> None:
            await self._inner.wait()

    async def fake_to_thread(func: object, *args: object, **kwargs: object) -> object:
        if func is main.run_configured_firehose_job:
            run_calls.append("firehose")
            if stop_event_ref:
                stop_event_ref[0].set()
            return success_firehose_result
        if func is main.run_configured_backfill_job:
            run_calls.append("backfill")
        return None

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "should_run_firehose_startup", lambda **kwargs: True)
    monkeypatch.setattr(main, "should_run_backfill_startup", lambda **kwargs: False)
    monkeypatch.setattr(main, "has_pending_bouncer_work", lambda: False)
    monkeypatch.setattr(main, "seconds_until_next_firehose_run", lambda now=None: 1800.0)
    monkeypatch.setattr(main, "seconds_until_next_backfill_run", lambda now=None: 1800.0)
    monkeypatch.setattr(main, "calculate_firehose_interval_seconds", lambda: 1800)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "Event", _CapturingEvent)
    caplog.set_level("INFO", logger=main.logger.name)

    asyncio.run(main.main())

    assert run_calls == ["firehose"]
    assert (
        "Skipping immediate follow-up Firehose pass; next run remains gated by the configured 1800s interval."
        in caplog.text
    )


def test_main_runs_startup_backfill_without_extra_sleep_when_firehose_is_skipped(
    monkeypatch,
) -> None:
    call_order: list[str] = []

    class StubSettings:
        github_provider_token_value = None

        class runtime:
            runtime_dir = None

        class provider:
            github_requests_per_minute = 60
            intake_pacing_seconds = 30
            firehose_interval_seconds = 1800
            firehose_per_page = 100
            firehose_pages = 1
            backfill_interval_seconds = 3600
            backfill_per_page = 100
            backfill_pages = 1
            backfill_window_days = 30
            backfill_min_created_date = "2008-01-01"

    success_backfill_result = BackfillRunResult(
        status=BackfillRunStatus.SUCCESS,
        outcomes=[],
        checkpoint=type("Checkpoint", (), {"exhausted": False})(),
        artifact_path=None,
        artifact_error=None,
    )

    _real_event_class = asyncio.Event
    stop_event_ref: list[asyncio.Event] = []

    class _CapturingEvent:
        def __init__(self) -> None:
            self._inner = _real_event_class()
            if not stop_event_ref:
                stop_event_ref.append(self._inner)

        def set(self) -> None:
            self._inner.set()

        def is_set(self) -> bool:
            return self._inner.is_set()

        async def wait(self) -> None:
            await self._inner.wait()

    async def fake_to_thread(func: object, *args: object, **kwargs: object) -> object:
        if func is main.run_configured_backfill_job:
            call_order.append("backfill")
            if stop_event_ref:
                stop_event_ref[0].set()
            return success_backfill_result
        call_order.append("sleep")
        return None

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "should_run_firehose_startup", lambda **kwargs: False)
    monkeypatch.setattr(main, "should_run_backfill_startup", lambda **kwargs: True)
    monkeypatch.setattr(main, "has_pending_bouncer_work", lambda: False)
    monkeypatch.setattr(main, "seconds_until_next_firehose_run", lambda now=None: 1800.0)
    monkeypatch.setattr(main, "seconds_until_next_backfill_run", lambda now=None: 1800.0)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "Event", _CapturingEvent)

    asyncio.run(main.main())

    assert call_order == ["backfill"]


def test_main_exits_on_startup_firehose_failure(monkeypatch) -> None:
    """A fatal exception during the startup Firehose pass must cause sys.exit(1)."""

    class StubSettings:
        github_provider_token_value = None

        class runtime:
            runtime_dir = None

        class provider:
            github_requests_per_minute = 60
            intake_pacing_seconds = 30
            firehose_interval_seconds = 3600
            firehose_per_page = 100
            firehose_pages = 1
            backfill_interval_seconds = 21600
            backfill_per_page = 100
            backfill_pages = 2
            backfill_window_days = 30
            backfill_min_created_date = "2008-01-01"

    def failing_job(**kwargs: object) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "should_run_firehose_startup", lambda **kwargs: True)
    monkeypatch.setattr(main, "has_pending_bouncer_work", lambda: False)
    monkeypatch.setattr(main, "run_configured_firehose_job", failing_job)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(main.main())

    assert exc_info.value.code == 1


def test_main_runs_firehose_on_interval_then_stops_on_signal(monkeypatch) -> None:
    """Worker runs startup Firehose/Backfill passes, then one due cycle, then exits cleanly."""
    run_calls: list[str] = []

    class StubSettings:
        github_provider_token_value = None

        class runtime:
            runtime_dir = None

        class provider:
            github_requests_per_minute = 60
            intake_pacing_seconds = 30
            firehose_interval_seconds = 3600
            firehose_per_page = 100
            firehose_pages = 1
            backfill_interval_seconds = 3600
            backfill_per_page = 100
            backfill_pages = 1
            backfill_window_days = 30
            backfill_min_created_date = "2008-01-01"

    success_firehose_result = FirehoseRunResult(
        status=FirehoseRunStatus.SUCCESS,
        outcomes=[],
        artifact_path=None,
        artifact_error=None,
    )
    success_backfill_result = BackfillRunResult(
        status=BackfillRunStatus.SUCCESS,
        outcomes=[],
        checkpoint=type("Checkpoint", (), {"exhausted": False})(),
        artifact_path=None,
        artifact_error=None,
    )

    # Capture the asyncio stop_event created inside main() so we can set it from
    # the fake to_thread, triggering a clean shutdown after the second run.
    _real_event_class = asyncio.Event
    stop_event_ref: list[asyncio.Event] = []

    class _CapturingEvent:
        """Wraps asyncio.Event and captures the first instance (the worker stop_event)."""

        def __init__(self) -> None:
            self._inner = _real_event_class()
            if not stop_event_ref:
                stop_event_ref.append(self._inner)

        def set(self) -> None:
            self._inner.set()

        def is_set(self) -> bool:
            return self._inner.is_set()

        async def wait(self) -> None:
            await self._inner.wait()

    async def fake_to_thread(func: object, *args: object, **kwargs: object) -> object:
        if func is main.run_configured_firehose_job:
            run_calls.append("firehose")
            if len(run_calls) >= 4 and stop_event_ref:
                stop_event_ref[0].set()
            return success_firehose_result
        if func is main.run_configured_backfill_job:
            run_calls.append("backfill")
            if len(run_calls) >= 4 and stop_event_ref:
                stop_event_ref[0].set()
            return success_backfill_result
        return None

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "should_run_firehose_startup", lambda **kwargs: True)
    monkeypatch.setattr(main, "should_run_backfill_startup", lambda **kwargs: True)
    monkeypatch.setattr(main, "has_pending_bouncer_work", lambda: False)
    monkeypatch.setattr(main, "has_pending_analyst_work", lambda: False)
    monkeypatch.setattr(main, "seconds_until_next_firehose_run", lambda now=None: 0.0)
    monkeypatch.setattr(main, "seconds_until_next_backfill_run", lambda now=None: 0.0)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "Event", _CapturingEvent)
    # Return 0 so asyncio.wait_for raises TimeoutError immediately — no real sleep.
    monkeypatch.setattr(main, "calculate_firehose_interval_seconds", lambda: 0)
    monkeypatch.setattr(main, "calculate_backfill_interval_seconds", lambda: 0)

    # main() exits cleanly when stop_event is set — no exception expected.
    asyncio.run(main.main())

    assert run_calls == ["firehose", "backfill", "firehose", "backfill"]

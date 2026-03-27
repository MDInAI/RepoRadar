from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
import sqlite3
import threading
import time

import pytest
from sqlalchemy.exc import OperationalError

from agentic_workers.core.events import DuplicateActiveAgentRunError
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
from agentic_workers.jobs.idea_scout_job import (
    IdeaScoutRunResult,
    IdeaScoutRunStatus,
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
    def __init__(
        self,
        *,
        github_token: str | None,
        github_tokens: tuple[str, ...] | list[str] | None = None,
        runtime_dir: Path | None = None,
    ) -> None:
        self.github_token = github_token
        self.github_tokens = tuple(github_tokens or ())
        self.runtime_dir = runtime_dir


class DummySession:
    def __init__(self, engine: object) -> None:
        self.engine = engine

    def __enter__(self) -> "DummySession":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def rollback(self) -> None:
        return None


async def _noop_pending_runner(**kwargs: object) -> bool:
    del kwargs
    return False


def test_configured_firehose_job_uses_settings_and_runtime_paths(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class StubSettings:
        github_provider_token_values = ("worker-token",)
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 3
            firehose_per_page = 100
            firehose_pages = 1
            firehose_search_lanes = 1
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
        lambda session, run_id, items_processed, items_succeeded, items_failed, **kwargs: None,
    )
    monkeypatch.setattr(
        main,
        "record_failed_agent_run",
        lambda session, run_id, error_summary, error_context, items_processed, items_succeeded, items_failed, **kwargs: None,
    )

    result = main.run_configured_firehose_job()

    assert result.status is FirehoseRunStatus.SUCCESS
    assert isinstance(captured["provider"], DummyProvider)
    assert captured["provider"].github_token == "worker-token"
    assert captured["runtime_dir"] == tmp_path
    assert captured["pacing_seconds"] == 3
    assert captured["modes"] == (FirehoseMode.NEW, FirehoseMode.TRENDING)
    assert captured["search_lanes"] == 1
    assert captured["agent_run_id"] == 11


def test_configured_firehose_job_skips_tracking_when_paused(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    cleared: dict[str, object] = {}

    class StubSettings:
        github_provider_token_values = ("worker-token",)
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 3
            firehose_per_page = 100
            firehose_pages = 1
            firehose_search_lanes = 1
            backfill_per_page = 50
            backfill_pages = 2
            backfill_window_days = 30
            backfill_min_created_date = "2008-01-01"
            backfill_interval_seconds = 3600

    def fake_run_firehose_job(**kwargs: object) -> FirehoseRunResult:
        captured.update(kwargs)
        return FirehoseRunResult(
            status=FirehoseRunStatus.SKIPPED_PAUSED,
            outcomes=[],
            artifact_path=None,
            artifact_error=None,
        )

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "GitHubFirehoseProvider", DummyProvider)
    monkeypatch.setattr(main, "Session", DummySession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "run_firehose_job", fake_run_firehose_job)
    monkeypatch.setattr(main, "is_agent_paused", lambda session, agent_name: True)
    monkeypatch.setattr(
        main,
        "clear_agent_progress_snapshot",
        lambda *, runtime_dir, agent_name: cleared.update(
            {"runtime_dir": runtime_dir, "agent_name": agent_name}
        ),
    )
    monkeypatch.setattr(
        main,
        "start_agent_run",
        lambda session, agent_name: pytest.fail("start_agent_run should not run while firehose is paused"),
    )

    result = main.run_configured_firehose_job()

    assert result.status is FirehoseRunStatus.SKIPPED_PAUSED
    assert cleared == {"runtime_dir": tmp_path, "agent_name": "firehose"}
    assert captured["agent_run_id"] is None


def test_configured_backfill_job_uses_settings_and_runtime_paths(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class StubSettings:
        github_provider_token_values = ("worker-token",)
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 3
            firehose_per_page = 100
            firehose_pages = 1
            firehose_search_lanes = 1
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
        lambda session, run_id, items_processed, items_succeeded, items_failed, **kwargs: None,
    )
    monkeypatch.setattr(
        main,
        "record_failed_agent_run",
        lambda session, run_id, error_summary, error_context, items_processed, items_succeeded, items_failed, **kwargs: None,
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


def test_configured_backfill_job_skips_tracking_when_paused(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    cleared: dict[str, object] = {}

    class StubSettings:
        github_provider_token_values = ("worker-token",)
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path

        class provider:
            github_requests_per_minute = 120
            intake_pacing_seconds = 3
            firehose_per_page = 100
            firehose_pages = 1
            firehose_search_lanes = 1
            backfill_per_page = 25
            backfill_pages = 2
            backfill_window_days = 14
            backfill_min_created_date = "2015-01-01"
            backfill_interval_seconds = 7200

    def fake_run_backfill_job(**kwargs: object) -> BackfillRunResult:
        captured.update(kwargs)
        return BackfillRunResult(
            status=BackfillRunStatus.SKIPPED_PAUSED,
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
    monkeypatch.setattr(main, "is_agent_paused", lambda session, agent_name: True)
    monkeypatch.setattr(
        main,
        "clear_agent_progress_snapshot",
        lambda *, runtime_dir, agent_name: cleared.update(
            {"runtime_dir": runtime_dir, "agent_name": agent_name}
        ),
    )
    monkeypatch.setattr(
        main,
        "start_agent_run",
        lambda session, agent_name: pytest.fail("start_agent_run should not run while backfill is paused"),
    )

    result = main.run_configured_backfill_job()

    assert result.status is BackfillRunStatus.SKIPPED_PAUSED
    assert cleared == {"runtime_dir": tmp_path, "agent_name": "backfill"}
    assert captured["agent_run_id"] is None


def test_configured_idea_scout_cycle_uses_settings_and_runtime_paths(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    class StubSettings:
        github_provider_token_values = ("worker-token", "backup-token")
        github_provider_token_value = "worker-token"

        class runtime:
            runtime_dir = tmp_path

        class provider:
            github_requests_per_minute = 30
            intake_pacing_seconds = 3
            idea_scout_per_page = 20
            idea_scout_pages_per_run = 2
            idea_scout_pacing_seconds = 2
            idea_scout_window_days = 14
            idea_scout_min_created_date = date(2020, 1, 1)

    def fake_run_idea_scout_cycle(**kwargs: object) -> IdeaScoutRunResult:
        captured.update(kwargs)
        return IdeaScoutRunResult(
            status=IdeaScoutRunStatus.SUCCESS,
            outcomes=[],
            searches_processed=0,
            artifact_path=None,
        )

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "GitHubFirehoseProvider", DummyProvider)
    monkeypatch.setattr(main, "Session", DummySession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "run_idea_scout_cycle", fake_run_idea_scout_cycle)
    monkeypatch.setattr(main, "start_agent_run", lambda session, agent_name: 17)
    monkeypatch.setattr(
        main,
        "finalize_agent_run",
        lambda session, run_id, items_processed, items_succeeded, items_failed, **kwargs: None,
    )
    monkeypatch.setattr(
        main,
        "record_failed_agent_run",
        lambda session, run_id, error_summary, error_context, items_processed, items_succeeded, items_failed, **kwargs: None,
    )

    result = main.run_configured_idea_scout_cycle()

    assert result.status is IdeaScoutRunStatus.SUCCESS
    assert isinstance(captured["provider"], DummyProvider)
    assert captured["provider"].github_token == "worker-token"
    assert captured["provider"].github_tokens == ("worker-token", "backup-token")
    assert captured["provider"].runtime_dir == tmp_path
    assert captured["runtime_dir"] == tmp_path
    assert captured["pacing_seconds"] == 2  # uses idea_scout_pacing_seconds, not intake_pacing_seconds
    assert captured["per_page"] == 20
    assert captured["pages_per_search"] == 2
    assert captured["window_days"] == 14
    assert captured["min_created_date"] == date(2020, 1, 1)


def test_calculate_idea_scout_run_timeout_scales_with_active_searches(monkeypatch) -> None:
    class StubSettings:
        class provider:
            idea_scout_pages_per_run = 3

    monkeypatch.setattr(main, "settings", StubSettings())

    timeout_seconds = main.calculate_idea_scout_run_timeout_seconds(active_search_count=4)

    assert timeout_seconds == 840


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
        lambda session, run_id, items_processed, items_succeeded, items_failed, **kwargs: None,
    )
    monkeypatch.setattr(
        main,
        "record_failed_agent_run",
        lambda session, run_id, error_summary, error_context, items_processed, items_succeeded, items_failed, **kwargs: None,
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
        ANALYST_PROVIDER = "heuristic"
        ANTHROPIC_API_KEY = None
        ANALYST_MODEL_NAME = "test-model"
        GEMINI_API_KEY = None
        GEMINI_BASE_URL = "https://example.test"
        GEMINI_MODEL_NAME = "gemini-test"

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
    monkeypatch.setattr(main, "create_analysis_provider", lambda *args: "heuristic-provider")
    monkeypatch.setattr(main, "Session", DummySession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "run_analyst_job", fake_run_analyst_job)
    monkeypatch.setattr(main, "start_agent_run", lambda session, agent_name: 44)
    monkeypatch.setattr(
        main,
        "finalize_agent_run",
        lambda session, run_id, items_processed, items_succeeded, items_failed, **kwargs: None,
    )
    monkeypatch.setattr(
        main,
        "record_failed_agent_run",
        lambda session, run_id, error_summary, error_context, items_processed, items_succeeded, items_failed, **kwargs: None,
    )

    result = main.run_configured_analyst_job()

    assert result.status is AnalystRunStatus.SUCCESS
    assert isinstance(captured["provider"], DummyProvider)
    assert captured["provider"].github_token == "worker-token"
    assert captured["runtime_dir"] == tmp_path
    assert captured["analysis_provider"] == "heuristic-provider"
    assert captured["agent_run_id"] == 44


def test_configured_analyst_job_clears_stale_progress_snapshot_when_paused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cleared: dict[str, object] = {}
    skipped: dict[str, object] = {}

    class StubSettings:
        github_provider_token_value = "worker-token"
        ANALYST_PROVIDER = "heuristic"
        ANTHROPIC_API_KEY = None
        ANALYST_MODEL_NAME = "test-model"
        GEMINI_API_KEY = None
        GEMINI_BASE_URL = "https://example.test"
        GEMINI_MODEL_NAME = "gemini-test"

        class runtime:
            runtime_dir = tmp_path

    def fake_run_analyst_job(**_: object) -> AnalystRunResult:
        return AnalystRunResult(
            status=AnalystRunStatus.SKIPPED_PAUSED,
            outcomes=[],
            artifact_path=None,
            artifact_error=None,
        )

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "GitHubFirehoseProvider", DummyProvider)
    monkeypatch.setattr(main, "create_analysis_provider", lambda *args: "heuristic-provider")
    monkeypatch.setattr(main, "Session", DummySession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "run_analyst_job", fake_run_analyst_job)
    monkeypatch.setattr(main, "start_agent_run", lambda session, agent_name: 55)
    monkeypatch.setattr(
        main,
        "clear_agent_progress_snapshot",
        lambda *, runtime_dir, agent_name: cleared.update(
            {"runtime_dir": runtime_dir, "agent_name": agent_name}
        ),
    )
    monkeypatch.setattr(
        main,
        "mark_agent_run_skipped",
        lambda session, run_id, **kwargs: skipped.update({"run_id": run_id, **kwargs}),
    )

    result = main.run_configured_analyst_job()

    assert result.status is AnalystRunStatus.SKIPPED_PAUSED
    assert cleared == {"runtime_dir": tmp_path, "agent_name": "analyst"}
    assert skipped["run_id"] == 55
    assert skipped["status"].value == "skipped_paused"


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
        **kwargs: object,
    ) -> None:
        del session, run_id, items_processed, items_succeeded, items_failed, kwargs
        raise RuntimeError("cannot persist terminal state")

    def capture_failed_run(
        session: object,
        run_id: int,
        error_summary: str,
        error_context: str | None,
        items_processed: int | None,
        items_succeeded: int | None,
        items_failed: int | None,
        **kwargs: object,
    ) -> None:
        del session, kwargs
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
        github_provider_token_values = ("token-1",)
        class provider:
            github_requests_per_minute = 20
            intake_pacing_seconds = 1
            firehose_pages = 2
            firehose_search_lanes = 1
            backfill_pages = 2

    monkeypatch.setattr(main, "settings", StubSettings())

    assert main.calculate_firehose_pacing_seconds() == 3


def test_calculate_firehose_interval_clamps_to_request_budget(monkeypatch) -> None:
    """Firehose interval is clamped against the combined Firehose + Backfill request budget."""

    class StubSettings:
        github_provider_token_values = ("token-1",)
        class provider:
            github_requests_per_minute = 20  # pacing = ceil(60/20) = 3s
            intake_pacing_seconds = 1  # lower than budget floor — floor wins
            firehose_interval_seconds = 1  # too small for (2 firehose modes × 2 pages + 1 backfill page) × 3s
            firehose_pages = 2
            firehose_search_lanes = 1
            backfill_pages = 1
            backfill_interval_seconds = 1

    monkeypatch.setattr(main, "settings", StubSettings())
    # (4 firehose requests + 1 backfill request) × 3s pacing = 15s minimum.
    assert main.calculate_firehose_interval_seconds() == 15


def test_calculate_backfill_interval_clamps_to_shared_request_budget(monkeypatch) -> None:
    class StubSettings:
        github_provider_token_values = ("token-1",)
        class provider:
            github_requests_per_minute = 20
            intake_pacing_seconds = 1
            firehose_interval_seconds = 3600
            firehose_pages = 2
            firehose_search_lanes = 1
            backfill_interval_seconds = 1
            backfill_pages = 2

    monkeypatch.setattr(main, "settings", StubSettings())

    # (4 firehose requests + 2 backfill requests) × 3s pacing = 18s minimum.
    assert main.calculate_backfill_interval_seconds() == 18


def test_calculate_backfill_interval_rejects_non_positive_config(monkeypatch) -> None:
    class StubSettings:
        github_provider_token_values = ("token-1",)
        class provider:
            github_requests_per_minute = 20
            intake_pacing_seconds = 1
            firehose_interval_seconds = 3600
            firehose_pages = 2
            firehose_search_lanes = 1
            backfill_interval_seconds = 0
            backfill_pages = 2

    monkeypatch.setattr(main, "settings", StubSettings())

    with pytest.raises(ValueError, match="backfill_interval_seconds must be greater than zero"):
        main.calculate_backfill_interval_seconds()


def test_acquire_worker_process_lock_raises_when_another_process_holds_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    real_flock = main.fcntl.flock
    state = {"acquired": False}

    def fake_flock(fd: int, operation: int) -> None:
        if operation == (main.fcntl.LOCK_EX | main.fcntl.LOCK_NB):
            if state["acquired"]:
                raise BlockingIOError("already locked")
            state["acquired"] = True
            return
        if operation == main.fcntl.LOCK_UN:
            state["acquired"] = False
            return
        real_flock(fd, operation)

    monkeypatch.setattr(main.fcntl, "flock", fake_flock)

    with main._acquire_worker_process_lock(tmp_path):
        with pytest.raises(main.WorkerAlreadyRunningError):
            with main._acquire_worker_process_lock(tmp_path):
                pass


@pytest.mark.asyncio
async def test_main_skips_duplicate_worker_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    startup_called = {"value": False}

    @contextmanager
    def duplicate_lock(_runtime_dir: Path | None):
        raise main.WorkerAlreadyRunningError(tmp_path / "locks" / "agentic-workers-main.lock", 1234)
        yield

    async def fake_run_worker_loop() -> None:
        startup_called["value"] = True

    monkeypatch.setattr(main, "_acquire_worker_process_lock", duplicate_lock)
    monkeypatch.setattr(main, "_run_worker_loop", fake_run_worker_loop)

    await main.main()

    assert startup_called["value"] is False


@pytest.mark.asyncio
async def test_run_due_intake_jobs_runs_firehose_and_backfill_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    barrier = threading.Barrier(2, timeout=1.0)
    calls: list[str] = []

    def fake_firehose(**_: object) -> FirehoseRunResult:
        calls.append("firehose")
        barrier.wait()
        return FirehoseRunResult(
            status=FirehoseRunStatus.SUCCESS,
            outcomes=[],
            artifact_path=None,
            artifact_error=None,
        )

    def fake_backfill(**_: object) -> BackfillRunResult:
        calls.append("backfill")
        barrier.wait()
        return BackfillRunResult(
            status=BackfillRunStatus.SUCCESS,
            outcomes=[],
            checkpoint=type("Checkpoint", (), {"exhausted": False})(),
            artifact_path=None,
            artifact_error=None,
        )

    monkeypatch.setattr(main, "run_configured_firehose_job", fake_firehose)
    monkeypatch.setattr(main, "run_configured_backfill_job", fake_backfill)
    monkeypatch.setattr(main, "_supports_parallel_intake_lanes", lambda: True)

    results = await main._run_due_intake_jobs(
        due_jobs=["firehose", "backfill"],
        thread_stop=threading.Event(),
    )

    assert set(calls) == {"firehose", "backfill"}
    assert isinstance(results["firehose"], FirehoseRunResult)
    assert isinstance(results["backfill"], BackfillRunResult)


@pytest.mark.asyncio
async def test_run_due_intake_jobs_serializes_for_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_order: list[str] = []

    def fake_firehose(**_: object) -> FirehoseRunResult:
        call_order.append("firehose")
        return FirehoseRunResult(
            status=FirehoseRunStatus.SUCCESS,
            outcomes=[],
            artifact_path=None,
            artifact_error=None,
        )

    def fake_backfill(**_: object) -> BackfillRunResult:
        call_order.append("backfill")
        return BackfillRunResult(
            status=BackfillRunStatus.SUCCESS,
            outcomes=[],
            checkpoint=type("Checkpoint", (), {"exhausted": False})(),
            artifact_path=None,
            artifact_error=None,
        )

    monkeypatch.setattr(main, "run_configured_firehose_job", fake_firehose)
    monkeypatch.setattr(main, "run_configured_backfill_job", fake_backfill)
    monkeypatch.setattr(main, "_supports_parallel_intake_lanes", lambda: False)

    results = await main._run_due_intake_jobs(
        due_jobs=["firehose", "backfill"],
        thread_stop=threading.Event(),
    )

    assert call_order == ["firehose", "backfill"]
    assert isinstance(results["firehose"], FirehoseRunResult)
    assert isinstance(results["backfill"], BackfillRunResult)


@pytest.mark.asyncio
async def test_run_due_intake_jobs_serial_sqlite_returns_duplicate_run_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_firehose(**_: object) -> FirehoseRunResult:
        raise main.DuplicateActiveAgentRunError("firehose")

    def fake_backfill(**_: object) -> BackfillRunResult:
        return BackfillRunResult(
            status=BackfillRunStatus.SUCCESS,
            outcomes=[],
            checkpoint=type("Checkpoint", (), {"exhausted": False})(),
            artifact_path=None,
            artifact_error=None,
        )

    monkeypatch.setattr(main, "run_configured_firehose_job", fake_firehose)
    monkeypatch.setattr(main, "run_configured_backfill_job", fake_backfill)
    monkeypatch.setattr(main, "_supports_parallel_intake_lanes", lambda: False)

    results = await main._run_due_intake_jobs(
        due_jobs=["firehose", "backfill"],
        thread_stop=threading.Event(),
    )

    assert isinstance(results["firehose"], main.DuplicateActiveAgentRunError)
    assert isinstance(results["backfill"], BackfillRunResult)


@pytest.mark.asyncio
async def test_run_due_intake_jobs_serial_sqlite_continues_after_firehose_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_order: list[str] = []

    def fake_firehose(**_: object) -> FirehoseRunResult:
        call_order.append("firehose")
        time.sleep(0.05)
        return FirehoseRunResult(
            status=FirehoseRunStatus.SUCCESS,
            outcomes=[],
            artifact_path=None,
            artifact_error=None,
        )

    def fake_backfill(**_: object) -> BackfillRunResult:
        call_order.append("backfill")
        return BackfillRunResult(
            status=BackfillRunStatus.SUCCESS,
            outcomes=[],
            checkpoint=type("Checkpoint", (), {"exhausted": False})(),
            artifact_path=None,
            artifact_error=None,
        )

    monkeypatch.setattr(main, "run_configured_firehose_job", fake_firehose)
    monkeypatch.setattr(main, "run_configured_backfill_job", fake_backfill)
    monkeypatch.setattr(main, "_supports_parallel_intake_lanes", lambda: False)
    monkeypatch.setattr(main, "calculate_firehose_run_timeout_seconds", lambda: 0.01)
    monkeypatch.setattr(main, "calculate_backfill_run_timeout_seconds", lambda: 60)

    results = await main._run_due_intake_jobs(
        due_jobs=["firehose", "backfill"],
        thread_stop=threading.Event(),
    )

    assert call_order == ["firehose", "backfill"]
    assert isinstance(results["firehose"], main.IntakeJobTimeoutError)
    assert isinstance(results["backfill"], BackfillRunResult)


def test_calculate_firehose_interval_uses_parallel_search_lanes(monkeypatch) -> None:
    class StubSettings:
        github_provider_token_values = ("token-1", "token-2", "token-3", "token-4")

        class provider:
            github_requests_per_minute = 20
            intake_pacing_seconds = 1
            firehose_interval_seconds = 1
            firehose_pages = 2
            firehose_search_lanes = 3
            backfill_pages = 1
            backfill_interval_seconds = 1

    monkeypatch.setattr(main, "settings", StubSettings())

    assert main.calculate_firehose_interval_seconds() == 6


def test_has_pending_analyst_work_queries_for_accepted_repositories(monkeypatch) -> None:
    class StubResult:
        def __init__(self, values: list[object]) -> None:
            self.values = values

        def all(self) -> list[object]:
            return self.values

    class StubSession:
        def __init__(self, engine: object) -> None:
            self.engine = engine
            self.exec_calls = 0

        def __enter__(self) -> "StubSession":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def exec(self, _statement: object) -> StubResult:
            self.exec_calls += 1
            if self.exec_calls == 1:
                repository = type(
                    "Repository",
                    (),
                    {
                        "github_repository_id": 123,
                        "analysis_status": RepositoryAnalysisStatus.PENDING,
                    },
                )()
                return StubResult([repository])
            return StubResult([])

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


def test_seconds_until_next_backfill_run_backs_off_when_checkpoint_is_exhausted(monkeypatch) -> None:
    class StubSession:
        def __init__(self, engine: object) -> None:
            self.engine = engine

        def __enter__(self) -> "StubSession":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    exhausted_checkpoint = BackfillCheckpointState(
        source_provider="github",
        window_start_date=date(2008, 1, 1),
        created_before_boundary=date(2008, 1, 1),
        created_before_cursor=None,
        next_page=1,
        exhausted=True,
        last_checkpointed_at=datetime(2026, 3, 8, 11, 30, tzinfo=timezone.utc),
        resume_required=False,
    )

    monkeypatch.setattr(main, "Session", StubSession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "load_backfill_progress", lambda _session: exhausted_checkpoint)
    monkeypatch.setattr(main, "calculate_exhausted_backfill_poll_seconds", lambda: 3600)

    remaining = main.seconds_until_next_backfill_run(
        now=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc).timestamp()
    )

    assert remaining == pytest.approx(3600.0)


def test_should_run_backfill_startup_skips_when_checkpoint_is_exhausted(monkeypatch) -> None:
    monkeypatch.setattr(main, "seconds_until_next_backfill_run", lambda now=None: 3600.0)

    assert main.should_run_backfill_startup() is False


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
            idea_scout_interval_seconds = 900

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
    monkeypatch.setattr(main, "validate_startup_recovery", lambda session: None)
    monkeypatch.setattr(main, "should_run_firehose_startup", lambda **kwargs: True)
    monkeypatch.setattr(main, "should_run_backfill_startup", lambda **kwargs: False)
    monkeypatch.setattr(main, "has_pending_bouncer_work", lambda: False)
    monkeypatch.setattr(main, "seconds_until_next_firehose_run", lambda now=None: 1800.0)
    monkeypatch.setattr(main, "seconds_until_next_backfill_run", lambda now=None: 1800.0)
    monkeypatch.setattr(main, "_run_bouncer_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_analyst_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_combiner_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_idea_scout_if_pending", _noop_pending_runner)
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
            idea_scout_interval_seconds = 900

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
    monkeypatch.setattr(main, "validate_startup_recovery", lambda session: None)
    monkeypatch.setattr(main, "should_run_firehose_startup", lambda **kwargs: True)
    monkeypatch.setattr(main, "should_run_backfill_startup", lambda **kwargs: False)
    monkeypatch.setattr(main, "has_pending_bouncer_work", lambda: False)
    monkeypatch.setattr(main, "seconds_until_next_firehose_run", lambda now=None: 1800.0)
    monkeypatch.setattr(main, "seconds_until_next_backfill_run", lambda now=None: 1800.0)
    monkeypatch.setattr(main, "calculate_firehose_interval_seconds", lambda: 1800)
    monkeypatch.setattr(main, "_run_bouncer_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_analyst_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_combiner_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_idea_scout_if_pending", _noop_pending_runner)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "Event", _CapturingEvent)
    caplog.set_level("INFO", logger=main.logger.name)

    asyncio.run(main.main())

    assert run_calls == ["firehose"]
    assert (
        "Skipping immediate follow-up Firehose pass; next run remains gated by the configured 1800s interval."
        in caplog.text
    )


def test_main_runs_startup_idea_scout_when_searches_are_pending(monkeypatch) -> None:
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
            idea_scout_interval_seconds = 900

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

    async def fake_run_idea_scout_if_pending(*, stop_event: asyncio.Event, thread_stop: threading.Event) -> bool:
        del stop_event, thread_stop
        call_order.append("idea_scout")
        if stop_event_ref:
            stop_event_ref[0].set()
        return True

    @contextmanager
    def fake_worker_lock(_runtime_dir: Path | None):
        yield

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "validate_startup_recovery", lambda session: None)
    monkeypatch.setattr(main, "should_run_firehose_startup", lambda **kwargs: False)
    monkeypatch.setattr(main, "should_run_backfill_startup", lambda **kwargs: False)
    monkeypatch.setattr(main, "_run_bouncer_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_analyst_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_combiner_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_idea_scout_if_pending", fake_run_idea_scout_if_pending)
    monkeypatch.setattr(main, "seconds_until_next_firehose_run", lambda now=None: 1800.0)
    monkeypatch.setattr(main, "seconds_until_next_backfill_run", lambda now=None: 1800.0)
    monkeypatch.setattr(main, "_acquire_worker_process_lock", fake_worker_lock)
    monkeypatch.setattr(asyncio, "Event", _CapturingEvent)

    asyncio.run(main.main())

    assert call_order == ["idea_scout"]


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
            idea_scout_interval_seconds = 900

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
        # Ignore rate-limit health polls and other housekeeping calls
        if func is main._poll_github_rate_limits:
            return None
        call_order.append("sleep")
        return None

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "validate_startup_recovery", lambda session: None)
    monkeypatch.setattr(main, "should_run_firehose_startup", lambda **kwargs: False)
    monkeypatch.setattr(main, "should_run_backfill_startup", lambda **kwargs: True)
    monkeypatch.setattr(main, "has_pending_bouncer_work", lambda: False)
    monkeypatch.setattr(main, "seconds_until_next_firehose_run", lambda now=None: 1800.0)
    monkeypatch.setattr(main, "seconds_until_next_backfill_run", lambda now=None: 1800.0)
    monkeypatch.setattr(main, "_run_bouncer_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_analyst_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_combiner_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_idea_scout_if_pending", _noop_pending_runner)
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
            idea_scout_interval_seconds = 900

    def failing_job(**kwargs: object) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "validate_startup_recovery", lambda session: None)
    monkeypatch.setattr(main, "should_run_firehose_startup", lambda **kwargs: True)
    monkeypatch.setattr(main, "has_pending_bouncer_work", lambda: False)
    monkeypatch.setattr(main, "run_configured_firehose_job", failing_job)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(main.main())

    assert exc_info.value.code == 1


def test_main_keeps_running_when_startup_firehose_hits_transient_sqlite_lock(monkeypatch) -> None:
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
            idea_scout_interval_seconds = 900

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

    locked = OperationalError("INSERT", {}, sqlite3.OperationalError("database is locked"))

    async def fake_run_due_intake_jobs(*, due_jobs: list[str], thread_stop: object) -> dict[str, object]:
        del due_jobs, thread_stop
        if stop_event_ref:
            stop_event_ref[0].set()
        return {"firehose": locked}

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "validate_startup_recovery", lambda session: None)
    monkeypatch.setattr(main, "should_run_firehose_startup", lambda **kwargs: True)
    monkeypatch.setattr(main, "should_run_backfill_startup", lambda **kwargs: False)
    monkeypatch.setattr(main, "has_pending_bouncer_work", lambda: False)
    monkeypatch.setattr(main, "has_pending_analyst_work", lambda: False)
    monkeypatch.setattr(main, "seconds_until_next_firehose_run", lambda now=None: 1800.0)
    monkeypatch.setattr(main, "seconds_until_next_backfill_run", lambda now=None: 1800.0)
    monkeypatch.setattr(main, "_run_due_intake_jobs", fake_run_due_intake_jobs)
    monkeypatch.setattr(main, "_run_bouncer_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_analyst_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_combiner_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_idea_scout_if_pending", _noop_pending_runner)
    monkeypatch.setattr(asyncio, "Event", _CapturingEvent)

    asyncio.run(main.main())


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
            idea_scout_interval_seconds = 900

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
    monkeypatch.setattr(main, "validate_startup_recovery", lambda session: None)
    monkeypatch.setattr(main, "should_run_firehose_startup", lambda **kwargs: True)
    monkeypatch.setattr(main, "should_run_backfill_startup", lambda **kwargs: True)
    monkeypatch.setattr(main, "has_pending_bouncer_work", lambda: False)
    monkeypatch.setattr(main, "has_pending_analyst_work", lambda: False)
    monkeypatch.setattr(main, "seconds_until_next_firehose_run", lambda now=None: 0.0)
    monkeypatch.setattr(main, "seconds_until_next_backfill_run", lambda now=None: 0.0)
    monkeypatch.setattr(main, "_run_bouncer_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_analyst_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_combiner_if_pending", _noop_pending_runner)
    monkeypatch.setattr(main, "_run_idea_scout_if_pending", _noop_pending_runner)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "Event", _CapturingEvent)
    # Return 0 so asyncio.wait_for raises TimeoutError immediately — no real sleep.
    monkeypatch.setattr(main, "calculate_firehose_interval_seconds", lambda: 0)
    monkeypatch.setattr(main, "calculate_backfill_interval_seconds", lambda: 0)

    # main() exits cleanly when stop_event is set — no exception expected.
    asyncio.run(main.main())

    assert run_calls == ["firehose", "backfill", "firehose", "backfill"]


def test_run_analyst_if_pending_skips_quietly_when_paused(monkeypatch) -> None:
    called = {"run": False}

    async def run_once() -> bool:
        stop_event = asyncio.Event()
        thread_stop = type("ThreadStop", (), {"is_set": lambda self: False})()
        return await main._run_analyst_if_pending(stop_event=stop_event, thread_stop=thread_stop)

    monkeypatch.setattr(main, "Session", DummySession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "is_agent_paused", lambda session, agent_name: True)
    monkeypatch.setattr(main, "has_pending_analyst_work", lambda: True)

    async def fake_to_thread(func: object, *args: object, **kwargs: object) -> object:
        called["run"] = True
        return None

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    assert asyncio.run(run_once()) is False
    assert called["run"] is False


def test_run_analyst_if_pending_skips_when_another_run_is_already_active(monkeypatch) -> None:
    async def run_once() -> bool:
        stop_event = asyncio.Event()
        thread_stop = type("ThreadStop", (), {"is_set": lambda self: False})()
        return await main._run_analyst_if_pending(stop_event=stop_event, thread_stop=thread_stop)

    monkeypatch.setattr(main, "Session", DummySession)
    monkeypatch.setattr(main, "engine", object())
    monkeypatch.setattr(main, "is_agent_paused", lambda session, agent_name: False)
    monkeypatch.setattr(main, "has_pending_analyst_work", lambda: True)

    async def fake_to_thread(func: object, *args: object, **kwargs: object) -> object:
        raise main.DuplicateActiveAgentRunError("analyst")

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    assert asyncio.run(run_once()) is False


def test_run_idea_scout_if_pending_skips_when_another_run_is_already_active(monkeypatch) -> None:
    async def run_once() -> bool:
        stop_event = asyncio.Event()
        thread_stop = type("ThreadStop", (), {"is_set": lambda self: False})()
        return await main._run_idea_scout_if_pending(stop_event=stop_event, thread_stop=thread_stop)

    monkeypatch.setattr(main, "count_pending_idea_scout_searches", lambda: 2)
    monkeypatch.setattr(main, "calculate_idea_scout_run_timeout_seconds", lambda active_search_count: 60)

    async def fake_to_thread(func: object, *args: object, **kwargs: object) -> object:
        raise DuplicateActiveAgentRunError("idea_scout")

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    assert asyncio.run(run_once()) is False


def test_run_idea_scout_if_pending_times_out_and_retries_later(monkeypatch) -> None:
    async def run_once() -> bool:
        stop_event = asyncio.Event()
        thread_stop = threading.Event()
        return await main._run_idea_scout_if_pending(stop_event=stop_event, thread_stop=thread_stop)

    monkeypatch.setattr(main, "count_pending_idea_scout_searches", lambda: 1)
    monkeypatch.setattr(main, "calculate_idea_scout_run_timeout_seconds", lambda active_search_count: 1)

    async def fake_wait_for(awaitable: object, timeout: float) -> object:
        if hasattr(awaitable, "close"):
            awaitable.close()
        del timeout
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    assert asyncio.run(run_once()) is False


def test_calculate_paused_poll_seconds_uses_floor(monkeypatch) -> None:
    monkeypatch.setattr(main, "calculate_intake_pacing_seconds", lambda: 3)
    assert main.calculate_paused_poll_seconds() == 15


def test_log_firehose_result_throttles_repeated_paused_poll_logs(caplog: pytest.LogCaptureFixture) -> None:
    main._last_paused_poll_log_at.clear()
    caplog.set_level("INFO")

    paused_result = FirehoseRunResult(
        status=FirehoseRunStatus.SKIPPED_PAUSED,
        outcomes=[],
        artifact_path=None,
        artifact_error=None,
    )

    main._log_firehose_result(paused_result)
    main._log_firehose_result(paused_result)

    paused_messages = [
        record.message for record in caplog.records if "Automatic checks will retry every" in record.message
    ]
    assert len(paused_messages) == 1

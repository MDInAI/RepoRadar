from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from agentic_workers.jobs.backfill_job import BackfillRunResult, BackfillRunStatus
from agentic_workers.jobs.firehose_job import FirehoseRunResult, FirehoseRunStatus
from agentic_workers.providers.github_provider import FirehoseMode
from agentic_workers.storage.backfill_progress import BackfillCheckpointState
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

    result = main.run_configured_firehose_job()

    assert result.status is FirehoseRunStatus.SUCCESS
    assert isinstance(captured["provider"], DummyProvider)
    assert captured["provider"].github_token == "worker-token"
    assert captured["runtime_dir"] == tmp_path
    assert captured["pacing_seconds"] == 3
    assert captured["modes"] == (FirehoseMode.NEW, FirehoseMode.TRENDING)


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
    monkeypatch.setattr(main, "should_run_backfill_startup", lambda: False)
    monkeypatch.setattr(main, "seconds_until_next_backfill_run", lambda now=None: 1800.0)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "Event", _CapturingEvent)

    asyncio.run(main.main())

    assert run_calls == ["firehose"]


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
    monkeypatch.setattr(main, "should_run_backfill_startup", lambda: True)
    monkeypatch.setattr(main, "seconds_until_next_backfill_run", lambda now=None: 0.0)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "Event", _CapturingEvent)
    # Return 0 so asyncio.wait_for raises TimeoutError immediately — no real sleep.
    monkeypatch.setattr(main, "calculate_firehose_interval_seconds", lambda: 0)
    monkeypatch.setattr(main, "calculate_backfill_interval_seconds", lambda: 0)

    # main() exits cleanly when stop_event is set — no exception expected.
    asyncio.run(main.main())

    assert run_calls == ["firehose", "backfill", "firehose", "backfill"]

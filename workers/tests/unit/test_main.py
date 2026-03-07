from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agentic_workers.jobs.firehose_job import FirehoseRunResult, FirehoseRunStatus
from agentic_workers.providers.github_provider import FirehoseMode
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


def test_firehose_pacing_respects_request_budget_floor(monkeypatch) -> None:
    class StubSettings:
        class provider:
            github_requests_per_minute = 20
            intake_pacing_seconds = 1

    monkeypatch.setattr(main, "settings", StubSettings())

    assert main.calculate_firehose_pacing_seconds() == 3


def test_calculate_firehose_interval_clamps_to_request_budget(monkeypatch) -> None:
    """Interval must be >= modes × pacing so the outer loop stays within the RPM budget."""

    class StubSettings:
        class provider:
            github_requests_per_minute = 20  # pacing = ceil(60/20) = 3s
            intake_pacing_seconds = 1  # lower than budget floor — floor wins
            firehose_interval_seconds = 1  # too small for 2 modes × 3s = 6s minimum

    monkeypatch.setattr(main, "settings", StubSettings())
    # 2 modes × 3s pacing = 6s minimum; configured 1s is clamped up
    assert main.calculate_firehose_interval_seconds() == 6


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

    def failing_job() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "run_configured_firehose_job", failing_job)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(main.main())

    assert exc_info.value.code == 1


def test_main_runs_firehose_on_interval_then_stops_on_signal(monkeypatch) -> None:
    """Worker runs a startup pass, then exactly one interval pass, then exits cleanly via signal."""
    run_calls: list[int] = []

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

    success_result = FirehoseRunResult(
        status=FirehoseRunStatus.SUCCESS,
        outcomes=[],
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

    async def fake_to_thread(func: object, *args: object, **kwargs: object) -> FirehoseRunResult:
        run_calls.append(1)
        if len(run_calls) >= 2 and stop_event_ref:
            # Signal clean shutdown after the second run (startup + first interval pass).
            stop_event_ref[0].set()
        return success_result

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "Event", _CapturingEvent)
    # Return 0 so asyncio.wait_for raises TimeoutError immediately — no real sleep.
    monkeypatch.setattr(main, "calculate_firehose_interval_seconds", lambda: 0)

    # main() exits cleanly when stop_event is set — no exception expected.
    asyncio.run(main.main())

    assert len(run_calls) == 2  # startup pass + exactly one interval pass

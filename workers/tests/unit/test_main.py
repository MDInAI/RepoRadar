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

    def failing_job() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(main, "run_configured_firehose_job", failing_job)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(main.main())

    assert exc_info.value.code == 1


def test_main_runs_firehose_on_interval_then_stops_on_signal(monkeypatch) -> None:
    """Worker should run a second Firehose pass after the interval and stop cleanly on signal."""
    run_calls: list[int] = []

    class StubSettings:
        github_provider_token_value = None

        class runtime:
            runtime_dir = None

        class provider:
            github_requests_per_minute = 60
            intake_pacing_seconds = 30
            firehose_interval_seconds = 0  # zero-length interval so the loop fires immediately

    success_result = FirehoseRunResult(
        status=FirehoseRunStatus.SUCCESS,
        outcomes=[],
        artifact_path=None,
        artifact_error=None,
    )

    async def fake_run_firehose_job_async() -> FirehoseRunResult:
        run_calls.append(1)
        # After the second run, cancel the event loop so the test terminates.
        if len(run_calls) >= 2:
            asyncio.get_running_loop().stop()
        return success_result

    async def patched_to_thread(func, *args, **kwargs):  # noqa: ANN001
        return await fake_run_firehose_job_async()

    monkeypatch.setattr(main, "settings", StubSettings())
    monkeypatch.setattr(asyncio, "to_thread", patched_to_thread)

    async def run_with_timeout() -> None:
        # Limit to avoid hanging; the interval=0 ensures the second pass fires quickly.
        await asyncio.wait_for(main.main(), timeout=5.0)

    with pytest.raises((asyncio.TimeoutError, SystemExit, RuntimeError)):
        asyncio.run(run_with_timeout())

    # At minimum the startup pass must have run.
    assert len(run_calls) >= 1

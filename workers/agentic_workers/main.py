from __future__ import annotations

import asyncio
import logging
import math
import signal
import sys
import threading
import time
from typing import Callable

from sqlmodel import Session

from agentic_workers.core.db import engine
from agentic_workers.core.config import settings
from agentic_workers.jobs.backfill_job import (
    BackfillRunResult,
    BackfillRunStatus,
    run_backfill_job,
)
from agentic_workers.jobs.firehose_job import FirehoseRunResult, FirehoseRunStatus, run_firehose_job
from agentic_workers.providers.github_provider import FirehoseMode, GitHubFirehoseProvider
from agentic_workers.storage.backfill_progress import load_backfill_progress

# Configure root logger
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


_FIREHOSE_MODES = (FirehoseMode.NEW, FirehoseMode.TRENDING)


def calculate_intake_pacing_seconds() -> int:
    request_budget_floor = math.ceil(60 / settings.provider.github_requests_per_minute)
    return max(settings.provider.intake_pacing_seconds, request_budget_floor)


def calculate_firehose_pacing_seconds() -> int:
    return calculate_intake_pacing_seconds()


def calculate_backfill_pacing_seconds() -> int:
    return calculate_intake_pacing_seconds()


def _calculate_shared_minimum_cycle_seconds(
    intake_pacing_seconds: int,
    firehose_pages: int,
    backfill_pages: int,
) -> int:
    firehose_requests = len(_FIREHOSE_MODES) * firehose_pages
    backfill_requests = backfill_pages
    return (firehose_requests + backfill_requests) * intake_pacing_seconds


def calculate_firehose_interval_seconds() -> int:
    """Return the outer loop interval, clamped so the run rate stays within the RPM budget.

    Firehose shares the GitHub token budget with Backfill, so the minimum safe cycle
    time is clamped against the combined request volume for both producers.
    """
    min_cycle = _calculate_shared_minimum_cycle_seconds(
        calculate_intake_pacing_seconds(),
        settings.provider.firehose_pages,
        settings.provider.backfill_pages,
    )
    return max(settings.provider.firehose_interval_seconds, min_cycle)


def calculate_backfill_interval_seconds() -> int:
    """Return the Backfill interval with the shared Firehose/Backfill RPM budget applied."""
    min_cycle = _calculate_shared_minimum_cycle_seconds(
        calculate_intake_pacing_seconds(),
        settings.provider.firehose_pages,
        settings.provider.backfill_pages,
    )
    return max(settings.provider.backfill_interval_seconds, min_cycle)


def run_configured_firehose_job(
    *,
    sleep_fn: Callable[[int], None] = time.sleep,
    should_stop: Callable[[], bool] | None = None,
) -> FirehoseRunResult:
    provider = GitHubFirehoseProvider(github_token=settings.github_provider_token_value)
    with Session(engine) as session:
        return run_firehose_job(
            session=session,
            provider=provider,
            runtime_dir=settings.runtime.runtime_dir,
            pacing_seconds=calculate_firehose_pacing_seconds(),
            modes=_FIREHOSE_MODES,
            per_page=settings.provider.firehose_per_page,
            pages=settings.provider.firehose_pages,
            sleep_fn=sleep_fn,
            should_stop=should_stop,
        )


def run_configured_backfill_job(
    *,
    sleep_fn: Callable[[int], None] = time.sleep,
    should_stop: Callable[[], bool] | None = None,
) -> BackfillRunResult:
    provider = GitHubFirehoseProvider(github_token=settings.github_provider_token_value)
    with Session(engine) as session:
        return run_backfill_job(
            session=session,
            provider=provider,
            runtime_dir=settings.runtime.runtime_dir,
            pacing_seconds=calculate_backfill_pacing_seconds(),
            per_page=settings.provider.backfill_per_page,
            pages=settings.provider.backfill_pages,
            window_days=settings.provider.backfill_window_days,
            min_created_date=settings.provider.backfill_min_created_date,
            sleep_fn=sleep_fn,
            should_stop=should_stop,
        )


def should_run_backfill_startup(*, now: float | None = None) -> bool:
    return seconds_until_next_backfill_run(now=now) <= 0


def seconds_until_next_backfill_run(*, now: float | None = None) -> float:
    current_time = now if now is not None else time.time()
    with Session(engine) as session:
        checkpoint = load_backfill_progress(session)
    if checkpoint is None:
        return 0.0

    if checkpoint.last_checkpointed_at is None:
        return calculate_backfill_interval_seconds()

    elapsed = current_time - checkpoint.last_checkpointed_at.timestamp()
    remaining = calculate_backfill_interval_seconds() - elapsed
    return max(0.0, remaining)


def _log_firehose_result(result: FirehoseRunResult) -> None:
    logger.info(
        "Firehose run complete: status=%s outcomes=%d",
        result.status,
        len(result.outcomes),
    )
    if result.artifact_error:
        logger.warning("Firehose runtime artifact write failed: %s", result.artifact_error)
    if result.status is not FirehoseRunStatus.SUCCESS:
        logger.warning("Firehose run completed with non-success status: %s", result.status)


def _log_backfill_result(result: BackfillRunResult) -> None:
    logger.info(
        "Backfill run complete: status=%s outcomes=%d exhausted=%s",
        result.status,
        len(result.outcomes),
        result.checkpoint.exhausted,
    )
    if result.artifact_error:
        logger.warning("Backfill runtime artifact write failed: %s", result.artifact_error)
    if result.status is not BackfillRunStatus.SUCCESS:
        logger.warning("Backfill run completed with non-success status: %s", result.status)


async def main():
    logger.info("Starting Agentic-Workflow worker processes...")

    stop_event = asyncio.Event()
    # Mirrors stop_event for threads: allows in-progress pacing sleeps to be
    # interrupted immediately on SIGINT/SIGTERM rather than waiting out the delay.
    _thread_stop = threading.Event()

    def handle_sigint():
        logger.info("Received stop signal. Shutting down...")
        stop_event.set()
        _thread_stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_sigint)

    def _interruptible_sleep(seconds: int) -> None:
        """Pacing sleep that returns early when a shutdown signal is received."""
        _thread_stop.wait(timeout=seconds)

    # Startup passes — any fatal failure stops the worker so the process supervisor
    # can restart it rather than leaving a silently broken worker running.
    try:
        firehose_result = await asyncio.to_thread(
            run_configured_firehose_job,
            sleep_fn=_interruptible_sleep,
            should_stop=_thread_stop.is_set,
        )
        _log_firehose_result(firehose_result)
        if not stop_event.is_set():
            await asyncio.to_thread(_interruptible_sleep, calculate_intake_pacing_seconds())
        if not stop_event.is_set() and should_run_backfill_startup():
            backfill_result = await asyncio.to_thread(
                run_configured_backfill_job,
                sleep_fn=_interruptible_sleep,
                should_stop=_thread_stop.is_set,
            )
            _log_backfill_result(backfill_result)
        elif not stop_event.is_set():
            logger.info(
                "Skipping startup Backfill pass; next run remains gated by the configured %ds interval.",
                calculate_backfill_interval_seconds(),
            )
    except Exception:
        logger.exception("Startup ingestion pass failed. Exiting.")
        sys.exit(1)

    logger.info(
        "Worker running. Next Firehose run in %ds. Next Backfill run in %ds. Press Ctrl+C to stop.",
        calculate_firehose_interval_seconds(),
        int(seconds_until_next_backfill_run()),
    )

    next_firehose_run_at = time.monotonic() + calculate_firehose_interval_seconds()
    # Resume the existing interval if we skipped the startup run, otherwise start a new interval
    next_backfill_run_at = time.monotonic() + seconds_until_next_backfill_run()

    # Continuous interval loop — individual run failures are logged but do not
    # stop the worker; only an unhandled startup failure is fatal.
    while not stop_event.is_set():
        next_due_at = min(next_firehose_run_at, next_backfill_run_at)
        timeout = max(0.0, next_due_at - time.monotonic())
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

        if stop_event.is_set():
            break

        due_jobs: list[str] = []
        now = time.monotonic()
        if now >= next_firehose_run_at:
            due_jobs.append("firehose")
        if now >= next_backfill_run_at:
            due_jobs.append("backfill")

        for index, job_name in enumerate(due_jobs):
            if stop_event.is_set():
                break

            try:
                if job_name == "firehose":
                    firehose_result = await asyncio.to_thread(
                        run_configured_firehose_job,
                        sleep_fn=_interruptible_sleep,
                        should_stop=_thread_stop.is_set,
                    )
                    _log_firehose_result(firehose_result)
                    next_firehose_run_at = time.monotonic() + calculate_firehose_interval_seconds()
                else:
                    backfill_result = await asyncio.to_thread(
                        run_configured_backfill_job,
                        sleep_fn=_interruptible_sleep,
                        should_stop=_thread_stop.is_set,
                    )
                    _log_backfill_result(backfill_result)
                    next_backfill_run_at = time.monotonic() + calculate_backfill_interval_seconds()
            except Exception:
                logger.exception("%s run failed. Continuing to next interval.", job_name.title())
                if job_name == "firehose":
                    next_firehose_run_at = time.monotonic() + calculate_firehose_interval_seconds()
                else:
                    # In case of failure, keep the interval logic to retry later rather than immediately
                    next_backfill_run_at = time.monotonic() + calculate_backfill_interval_seconds()

            if index < len(due_jobs) - 1 and not stop_event.is_set():
                await asyncio.to_thread(_interruptible_sleep, calculate_intake_pacing_seconds())

    logger.info("Worker shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)

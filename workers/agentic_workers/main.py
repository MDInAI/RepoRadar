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
from agentic_workers.jobs.firehose_job import FirehoseRunResult, FirehoseRunStatus, run_firehose_job
from agentic_workers.providers.github_provider import FirehoseMode, GitHubFirehoseProvider

# Configure root logger
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


_FIREHOSE_MODES = (FirehoseMode.NEW, FirehoseMode.TRENDING)


def calculate_firehose_pacing_seconds() -> int:
    request_budget_floor = math.ceil(60 / settings.provider.github_requests_per_minute)
    return max(settings.provider.intake_pacing_seconds, request_budget_floor)


def calculate_firehose_interval_seconds() -> int:
    """Return the outer loop interval, clamped so the run rate stays within the RPM budget.

    A single Firehose cycle issues one API request per mode. The minimum safe cycle
    time is therefore ``len(modes) × pacing_seconds``; any shorter interval would
    exceed the configured ``github_requests_per_minute`` budget.
    """
    pacing = calculate_firehose_pacing_seconds()
    minimum_safe_interval = len(_FIREHOSE_MODES) * pacing
    return max(settings.provider.firehose_interval_seconds, minimum_safe_interval)


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

    # Startup pass — a total failure stops the worker so the process supervisor
    # can detect and restart it rather than leaving a silently broken worker running.
    try:
        result = await asyncio.to_thread(
            run_configured_firehose_job,
            sleep_fn=_interruptible_sleep,
            should_stop=_thread_stop.is_set,
        )
        _log_firehose_result(result)
    except Exception:
        logger.exception("Startup Firehose ingestion pass failed. Exiting.")
        sys.exit(1)

    interval = calculate_firehose_interval_seconds()
    logger.info(
        "Worker running. Next Firehose run in %ds. Press Ctrl+C to stop.", interval
    )

    # Continuous interval loop — individual run failures are logged but do not
    # stop the worker; only an unhandled startup failure is fatal.
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass

        if stop_event.is_set():
            break

        try:
            result = await asyncio.to_thread(
                run_configured_firehose_job,
                sleep_fn=_interruptible_sleep,
                should_stop=_thread_stop.is_set,
            )
            _log_firehose_result(result)
        except Exception:
            logger.exception("Firehose run failed. Continuing to next interval.")

    logger.info("Worker shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)

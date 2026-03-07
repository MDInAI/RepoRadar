from __future__ import annotations

import asyncio
import logging
import math
import signal
import sys
import time

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


def calculate_firehose_pacing_seconds() -> int:
    request_budget_floor = math.ceil(60 / settings.provider.github_requests_per_minute)
    return max(settings.provider.intake_pacing_seconds, request_budget_floor)


def run_configured_firehose_job():
    provider = GitHubFirehoseProvider(github_token=settings.github_provider_token_value)
    with Session(engine) as session:
        return run_firehose_job(
            session=session,
            provider=provider,
            runtime_dir=settings.runtime.runtime_dir,
            pacing_seconds=calculate_firehose_pacing_seconds(),
            modes=(FirehoseMode.NEW, FirehoseMode.TRENDING),
            sleep_fn=time.sleep,
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

    def handle_sigint():
        logger.info("Received stop signal. Shutting down...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_sigint)

    # Startup pass — a total failure stops the worker so the process supervisor
    # can detect and restart it rather than leaving a silently broken worker running.
    try:
        result = await asyncio.to_thread(run_configured_firehose_job)
        _log_firehose_result(result)
    except Exception:
        logger.exception("Startup Firehose ingestion pass failed. Exiting.")
        sys.exit(1)

    interval = settings.provider.firehose_interval_seconds
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
            result = await asyncio.to_thread(run_configured_firehose_job)
            _log_firehose_result(result)
        except Exception:
            logger.exception("Firehose run failed. Continuing to next interval.")

    logger.info("Worker shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)

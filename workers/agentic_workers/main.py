from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import logging
import math
import os
import signal
import sys
import threading
import time
import traceback
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Callable
from typing import TypeVar

from sqlalchemy import func
from sqlmodel import Session, select

from agentic_workers.core.db import engine
from agentic_workers.core.config import settings
from agentic_workers.core.events import (
    DuplicateActiveAgentRunError,
    complete_agent_run as finalize_agent_run,
    fail_agent_run as record_failed_agent_run,
    mark_agent_run_skipped,
    start_agent_run,
)
from agentic_workers.core.pause_manager import is_agent_paused
from agentic_workers.core.recovery import validate_startup_recovery
from agentic_workers.jobs.backfill_job import (
    BackfillRunResult,
    BackfillRunStatus,
    run_backfill_job,
)
from agentic_workers.jobs.analyst_job import (
    AnalystRunResult,
    AnalystRunStatus,
    run_analyst_job,
)
from agentic_workers.jobs.bouncer_job import (
    BouncerRunResult,
    BouncerRunStatus,
    run_bouncer_job,
)
from agentic_workers.jobs.combiner_job import (
    CombinerRunResult,
    CombinerRunStatus,
    run_combiner_job,
)
from agentic_workers.jobs.firehose_job import FirehoseRunResult, FirehoseRunStatus, run_firehose_job
from agentic_workers.providers.github_provider import FirehoseMode, GitHubFirehoseProvider
from agentic_workers.providers.readme_analyst import create_analysis_provider
from agentic_workers.storage.backfill_progress import load_backfill_progress
from agentic_workers.storage.agent_progress_snapshots import clear_agent_progress_snapshot
from agentic_workers.storage.backend_models import (
    AgentRunStatus,
    RepositoryAnalysisStatus,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
    SynthesisRun,
    SynthesisRunStatus,
)
from agentic_workers.storage.firehose_progress import load_firehose_progress
from agentic_workers.storage.analysis_store import list_pending_analysis_targets

# Configure root logger
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


_FIREHOSE_MODES = (FirehoseMode.NEW, FirehoseMode.TRENDING)
_MIN_FIREHOSE_RUN_TIMEOUT_SECONDS = 15 * 60
_MIN_BACKFILL_RUN_TIMEOUT_SECONDS = 10 * 60
_ESTIMATED_GITHUB_REQUEST_BUDGET_SECONDS = 60
_TIMEOUT_BUFFER_SECONDS = 120
_WORKER_PROCESS_LOCK_FILENAME = "agentic-workers-main.lock"
ResultT = TypeVar("ResultT")


class IntakeJobTimeoutError(TimeoutError):
    def __init__(self, agent_name: str, timeout_seconds: float) -> None:
        self.agent_name = agent_name
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"{agent_name} run exceeded the watchdog timeout of {int(timeout_seconds)}s."
        )


class WorkerAlreadyRunningError(RuntimeError):
    def __init__(self, path: Path, holder_pid: int | None = None) -> None:
        self.path = path
        self.holder_pid = holder_pid
        pid_suffix = f" (pid {holder_pid})" if holder_pid is not None else ""
        super().__init__(f"Another worker instance already holds {path}{pid_suffix}.")


@dataclass(frozen=True, slots=True)
class AgentRunMetrics:
    items_processed: int
    items_succeeded: int
    items_failed: int
    error_summary: str | None = None
    error_context: str | None = None
    provider_name: str | None = None
    model_name: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


def calculate_intake_pacing_seconds() -> int:
    request_budget_floor = math.ceil(60 / settings.provider.github_requests_per_minute)
    return max(settings.provider.intake_pacing_seconds, request_budget_floor)


def calculate_firehose_pacing_seconds() -> int:
    return calculate_intake_pacing_seconds()


def calculate_backfill_pacing_seconds() -> int:
    return calculate_intake_pacing_seconds()


def calculate_paused_poll_seconds() -> int:
    return max(15, calculate_intake_pacing_seconds())


def _calculate_shared_minimum_cycle_seconds(
    intake_pacing_seconds: int,
    github_token_count: int,
    firehose_pages: int,
    firehose_search_lanes: int,
    backfill_pages: int,
) -> int:
    firehose_requests = len(_FIREHOSE_MODES) * firehose_pages
    backfill_requests = backfill_pages
    parallelism = max(1, min(max(github_token_count, 1), max(firehose_search_lanes, 1) + 1))
    return math.ceil((firehose_requests + backfill_requests) / parallelism) * intake_pacing_seconds


def _configured_github_token_count() -> int:
    token_values = getattr(settings, "github_provider_token_values", None)
    if token_values is not None:
        return max(1, len(token_values))
    primary_token = getattr(settings, "github_provider_token_value", None)
    return 1 if primary_token is not None else 1


def calculate_firehose_interval_seconds() -> int:
    """Return the outer loop interval, clamped so the run rate stays within the RPM budget.

    Firehose shares the GitHub token budget with Backfill, so the minimum safe cycle
    time is clamped against the combined request volume for both producers.
    """
    min_cycle = _calculate_shared_minimum_cycle_seconds(
        calculate_intake_pacing_seconds(),
        _configured_github_token_count(),
        settings.provider.firehose_pages,
        getattr(settings.provider, "firehose_search_lanes", 1),
        settings.provider.backfill_pages,
    )
    return max(settings.provider.firehose_interval_seconds, min_cycle)


def calculate_backfill_interval_seconds() -> int:
    """Return the Backfill interval with the shared Firehose/Backfill RPM budget applied."""
    if settings.provider.backfill_interval_seconds <= 0:
        raise ValueError("backfill_interval_seconds must be greater than zero")

    min_cycle = _calculate_shared_minimum_cycle_seconds(
        calculate_intake_pacing_seconds(),
        _configured_github_token_count(),
        settings.provider.firehose_pages,
        getattr(settings.provider, "firehose_search_lanes", 1),
        settings.provider.backfill_pages,
    )
    return max(settings.provider.backfill_interval_seconds, min_cycle)


def calculate_firehose_run_timeout_seconds() -> int:
    request_count = len(_FIREHOSE_MODES) * settings.provider.firehose_pages
    parallelism = max(
        1,
        min(_configured_github_token_count(), max(getattr(settings.provider, "firehose_search_lanes", 1), 1) + 1),
    )
    estimated = math.ceil(request_count / parallelism) * _ESTIMATED_GITHUB_REQUEST_BUDGET_SECONDS
    return max(_MIN_FIREHOSE_RUN_TIMEOUT_SECONDS, estimated + _TIMEOUT_BUFFER_SECONDS)


def calculate_backfill_run_timeout_seconds() -> int:
    request_count = max(settings.provider.backfill_pages, 1)
    estimated = request_count * _ESTIMATED_GITHUB_REQUEST_BUDGET_SECONDS
    return max(_MIN_BACKFILL_RUN_TIMEOUT_SECONDS, estimated + _TIMEOUT_BUFFER_SECONDS)


def run_configured_firehose_job(
    *,
    sleep_fn: Callable[[int], None] = time.sleep,
    should_stop: Callable[[], bool] | None = None,
) -> FirehoseRunResult:
    github_tokens = getattr(settings, "github_provider_token_values", ())
    provider_kwargs = dict(
        github_token=settings.github_provider_token_value,
        runtime_dir=settings.runtime.runtime_dir,
    )
    if github_tokens:
        provider_kwargs["github_tokens"] = github_tokens
    provider = GitHubFirehoseProvider(**provider_kwargs)
    with Session(engine) as session:
        return _run_tracked_job(
            session=session,
            agent_name="firehose",
            runtime_dir=settings.runtime.runtime_dir,
            execute_job=lambda run_id: run_firehose_job(
                session=session,
                provider=provider,
                runtime_dir=settings.runtime.runtime_dir,
                pacing_seconds=calculate_firehose_pacing_seconds(),
                modes=_FIREHOSE_MODES,
                per_page=settings.provider.firehose_per_page,
                pages=settings.provider.firehose_pages,
                search_lanes=getattr(settings.provider, "firehose_search_lanes", 1),
                sleep_fn=sleep_fn,
                should_stop=should_stop,
                agent_run_id=run_id,
            ),
            summarize_run=_summarize_firehose_run,
            is_success=lambda result: result.status is FirehoseRunStatus.SUCCESS,
            is_skipped=lambda result: result.status
            in (
                FirehoseRunStatus.SKIPPED,
                FirehoseRunStatus.SKIPPED_PAUSED,
            ),
            is_paused_skip=lambda result: result.status is FirehoseRunStatus.SKIPPED_PAUSED,
            skipped_reason="firehose run skipped because shutdown was requested.",
        )


def run_configured_backfill_job(
    *,
    sleep_fn: Callable[[int], None] = time.sleep,
    should_stop: Callable[[], bool] | None = None,
) -> BackfillRunResult:
    github_tokens = getattr(settings, "github_provider_token_values", ())
    provider_kwargs = dict(
        github_token=settings.github_provider_token_value,
        runtime_dir=settings.runtime.runtime_dir,
    )
    if github_tokens:
        provider_kwargs["github_tokens"] = github_tokens
    provider = GitHubFirehoseProvider(**provider_kwargs)
    with Session(engine) as session:
        return _run_tracked_job(
            session=session,
            agent_name="backfill",
            runtime_dir=settings.runtime.runtime_dir,
            execute_job=lambda run_id: run_backfill_job(
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
                agent_run_id=run_id,
            ),
            summarize_run=_summarize_backfill_run,
            is_success=lambda result: result.status is BackfillRunStatus.SUCCESS,
            is_skipped=lambda result: result.status
            in (
                BackfillRunStatus.SKIPPED,
                BackfillRunStatus.SKIPPED_PAUSED,
            ),
            is_paused_skip=lambda result: result.status is BackfillRunStatus.SKIPPED_PAUSED,
            skipped_reason="backfill run skipped because shutdown was requested.",
        )


def run_configured_bouncer_job(
    *,
    should_stop: Callable[[], bool] | None = None,
) -> BouncerRunResult:
    with Session(engine) as session:
        return _run_tracked_job(
            session=session,
            agent_name="bouncer",
            runtime_dir=settings.runtime.runtime_dir,
            execute_job=lambda run_id: run_bouncer_job(
                session=session,
                runtime_dir=settings.runtime.runtime_dir,
                include_rules=settings.provider.bouncer_include_rules,
                exclude_rules=settings.provider.bouncer_exclude_rules,
                should_stop=should_stop,
                agent_run_id=run_id,
            ),
            summarize_run=_summarize_bouncer_run,
            is_success=lambda result: result.status is BouncerRunStatus.SUCCESS,
            is_skipped=lambda result: result.status
            in (
                BouncerRunStatus.SKIPPED,
                BouncerRunStatus.SKIPPED_PAUSED,
            ),
            is_paused_skip=lambda result: result.status is BouncerRunStatus.SKIPPED_PAUSED,
            skipped_reason="bouncer run skipped because shutdown was requested.",
        )


def run_configured_analyst_job(
    *,
    should_stop: Callable[[], bool] | None = None,
) -> AnalystRunResult:
    github_tokens = getattr(settings, "github_provider_token_values", ())
    gemini_keys = getattr(settings, "gemini_api_key_values", ())
    provider_kwargs = dict(
        github_token=settings.github_provider_token_value,
        runtime_dir=settings.runtime.runtime_dir,
    )
    if github_tokens:
        provider_kwargs["github_tokens"] = github_tokens
    provider = GitHubFirehoseProvider(**provider_kwargs)
    api_key = settings.ANTHROPIC_API_KEY.get_secret_value() if settings.ANTHROPIC_API_KEY else None
    gemini_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None
    analysis_provider = create_analysis_provider(
        settings.ANALYST_PROVIDER,
        api_key,
        settings.ANALYST_MODEL_NAME,
        gemini_key,
        gemini_keys,
        settings.GEMINI_BASE_URL,
        settings.GEMINI_MODEL_NAME,
        settings.runtime.runtime_dir,
    )
    with Session(engine) as session:
        return _run_tracked_job(
            session=session,
            agent_name="analyst",
            runtime_dir=settings.runtime.runtime_dir,
            execute_job=lambda run_id: run_analyst_job(
                session=session,
                provider=provider,
                runtime_dir=settings.runtime.runtime_dir,
                analysis_provider=analysis_provider,
                should_stop=should_stop,
                agent_run_id=run_id,
            ),
            summarize_run=_summarize_analyst_run,
            is_success=lambda result: result.status is AnalystRunStatus.SUCCESS,
            is_skipped=lambda result: result.status
            in (
                AnalystRunStatus.SKIPPED,
                AnalystRunStatus.SKIPPED_PAUSED,
            ),
            is_paused_skip=lambda result: result.status is AnalystRunStatus.SKIPPED_PAUSED,
            skipped_reason="analyst run skipped because shutdown was requested.",
        )


def should_run_backfill_startup(*, now: float | None = None) -> bool:
    return seconds_until_next_backfill_run(now=now) <= 0


def has_pending_bouncer_work() -> bool:
    with Session(engine) as session:
        pending_count = session.exec(
            select(func.count(RepositoryIntake.github_repository_id))
            .where(RepositoryIntake.queue_status == RepositoryQueueStatus.PENDING)
            .where(RepositoryIntake.triage_status == RepositoryTriageStatus.PENDING)
        ).one()
    return int(pending_count or 0) > 0


def has_pending_analyst_work() -> bool:
    with Session(engine) as session:
        return bool(list_pending_analysis_targets(session))


def has_pending_combiner_work() -> bool:
    with Session(engine) as session:
        pending_count = session.exec(
            select(func.count(SynthesisRun.id))
            .where(SynthesisRun.status == SynthesisRunStatus.PENDING)
            .where(SynthesisRun.run_type == "combiner")
        ).one()
    return int(pending_count or 0) > 0


def seconds_until_next_firehose_run(*, now: float | None = None) -> float:
    current_time = now if now is not None else time.time()
    with Session(engine) as session:
        checkpoint = load_firehose_progress(session)
    if checkpoint is None:
        # Fresh database — run Firehose immediately on first install.
        return 0.0
    if checkpoint.resume_required:
        return 0.0
    if checkpoint.last_checkpointed_at is None:
        return 0.0
    elapsed = current_time - checkpoint.last_checkpointed_at.timestamp()
    remaining = calculate_firehose_interval_seconds() - elapsed
    return max(0.0, remaining)


def should_run_firehose_startup(*, now: float | None = None) -> bool:
    return seconds_until_next_firehose_run(now=now) <= 0


def seconds_until_next_backfill_run(*, now: float | None = None) -> float:
    current_time = now if now is not None else time.time()
    with Session(engine) as session:
        checkpoint = load_backfill_progress(session)
    if checkpoint is None:
        # Fresh database — run Backfill immediately so the intake surface is
        # populated on first install without waiting a full interval.
        return 0.0
    if checkpoint.resume_required:
        return 0.0
    if checkpoint.last_checkpointed_at is None:
        return 0.0

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
    if result.status is FirehoseRunStatus.SKIPPED_PAUSED:
        logger.info("Firehose remains paused; next automatic pause check will back off.")
    elif result.status is not FirehoseRunStatus.SUCCESS:
        logger.warning("Firehose run completed with non-success status: %s", result.status)


def _log_intake_timeout(error: IntakeJobTimeoutError) -> None:
    logger.error(
        "%s did not finish within %ss. The scheduler will stop waiting on it and continue other work.",
        error.agent_name.title(),
        int(error.timeout_seconds),
    )


def _log_backfill_result(result: BackfillRunResult) -> None:
    logger.info(
        "Backfill run complete: status=%s outcomes=%d exhausted=%s",
        result.status,
        len(result.outcomes),
        result.checkpoint.exhausted,
    )
    if result.artifact_error:
        logger.warning("Backfill runtime artifact write failed: %s", result.artifact_error)
    if result.status is BackfillRunStatus.SKIPPED_PAUSED:
        logger.info("Backfill remains paused; next automatic pause check will back off.")
    elif result.status is not BackfillRunStatus.SUCCESS:
        logger.warning("Backfill run completed with non-success status: %s", result.status)


def _log_bouncer_result(result: BouncerRunResult) -> None:
    logger.info(
        "Bouncer run complete: status=%s outcomes=%d",
        result.status,
        len(result.outcomes),
    )
    if result.artifact_error:
        logger.warning("Bouncer runtime artifact write failed: %s", result.artifact_error)
    if result.status is BouncerRunStatus.SKIPPED_PAUSED:
        logger.info("Bouncer remains paused; queue polling will back off.")
    elif result.status is not BouncerRunStatus.SUCCESS:
        logger.warning("Bouncer run completed with non-success status: %s", result.status)


def _log_analyst_result(result: AnalystRunResult) -> None:
    logger.info(
        "Analyst run complete: status=%s outcomes=%d",
        result.status,
        len(result.outcomes),
    )
    if result.artifact_error:
        logger.warning("Analyst runtime artifact write failed: %s", result.artifact_error)
    if result.status is AnalystRunStatus.SKIPPED_PAUSED:
        logger.info("Analyst remains paused; queue polling will back off.")
    elif result.status is not AnalystRunStatus.SUCCESS:
        logger.warning("Analyst run completed with non-success status: %s", result.status)


def _log_combiner_result(result: CombinerRunResult) -> None:
    logger.info(
        "Combiner run complete: status=%s provider=%s model=%s total_tokens=%s",
        result.status,
        result.provider_name or "n/a",
        result.model_name or "n/a",
        result.total_tokens,
    )
    if result.error_message:
        logger.warning("Combiner run failed with error: %s", result.error_message)


def _record_run_outcome(
    session: Session,
    run_id: int,
    succeeded: bool,
    metrics: AgentRunMetrics,
) -> None:
    if succeeded:
        finalize_agent_run(
            session,
            run_id,
            items_processed=metrics.items_processed,
            items_succeeded=metrics.items_succeeded,
            items_failed=metrics.items_failed,
            provider_name=metrics.provider_name,
            model_name=metrics.model_name,
            input_tokens=metrics.input_tokens,
            output_tokens=metrics.output_tokens,
            total_tokens=metrics.total_tokens,
        )
        return

    record_failed_agent_run(
        session,
        run_id,
        error_summary=metrics.error_summary or "agent run failed",
        error_context=metrics.error_context,
        items_processed=metrics.items_processed,
        items_succeeded=metrics.items_succeeded,
        items_failed=metrics.items_failed,
        provider_name=metrics.provider_name,
        model_name=metrics.model_name,
        input_tokens=metrics.input_tokens,
        output_tokens=metrics.output_tokens,
        total_tokens=metrics.total_tokens,
    )


def _run_tracked_job(
    *,
    session: Session,
    agent_name: str,
    runtime_dir: Path | None,
    execute_job: Callable[[int], ResultT],
    summarize_run: Callable[[ResultT], AgentRunMetrics],
    is_success: Callable[[ResultT], bool],
    is_skipped: Callable[[ResultT], bool],
    is_paused_skip: Callable[[ResultT], bool],
    skipped_reason: str,
) -> ResultT:
    run_id: int | None = None
    metrics: AgentRunMetrics | None = None
    failure_phase = "run execution"
    try:
        run_id = start_agent_run(session, agent_name)
        result = execute_job(run_id)
        metrics = summarize_run(result)
        failure_phase = "persisting terminal state"
        if is_skipped(result):
            paused_skip = is_paused_skip(result)
            if paused_skip:
                clear_agent_progress_snapshot(runtime_dir=runtime_dir, agent_name=agent_name)
            mark_agent_run_skipped(
                session,
                run_id,
                reason=f"{agent_name} paused by policy." if paused_skip else skipped_reason,
                status=(
                    AgentRunStatus.SKIPPED_PAUSED
                    if paused_skip
                    else AgentRunStatus.SKIPPED
                ),
                items_processed=metrics.items_processed,
                items_succeeded=metrics.items_succeeded,
                items_failed=metrics.items_failed,
                provider_name=metrics.provider_name,
                model_name=metrics.model_name,
                input_tokens=metrics.input_tokens,
                output_tokens=metrics.output_tokens,
                total_tokens=metrics.total_tokens,
            )
        else:
            _record_run_outcome(session, run_id, is_success(result), metrics)
        return result
    except Exception as exc:
        session.rollback()
        if run_id is not None:
            _record_unexpected_run_failure(
                session,
                run_id,
                agent_name=agent_name,
                exc=exc,
                metrics=metrics,
                phase=failure_phase,
            )
        raise


def _record_unexpected_run_failure(
    session: Session,
    run_id: int,
    *,
    agent_name: str,
    exc: Exception,
    metrics: AgentRunMetrics | None,
    phase: str,
) -> None:
    if phase == "persisting terminal state":
        error_summary = f"{agent_name} run crashed while persisting terminal state: {exc}"
    else:
        error_summary = f"{agent_name} run crashed: {exc}"

    payload = _unexpected_exception_payload(exc)
    payload["phase"] = phase
    if metrics is not None:
        payload["metrics"] = metrics

    record_failed_agent_run(
        session,
        run_id,
        error_summary=error_summary,
        error_context=_serialize_json(payload),
        items_processed=metrics.items_processed if metrics is not None else None,
        items_succeeded=metrics.items_succeeded if metrics is not None else None,
        items_failed=metrics.items_failed if metrics is not None else None,
        provider_name=metrics.provider_name if metrics is not None else None,
        model_name=metrics.model_name if metrics is not None else None,
        input_tokens=metrics.input_tokens if metrics is not None else None,
        output_tokens=metrics.output_tokens if metrics is not None else None,
        total_tokens=metrics.total_tokens if metrics is not None else None,
    )


def _summarize_firehose_run(result: FirehoseRunResult) -> AgentRunMetrics:
    items_processed = sum(outcome.fetched_count for outcome in result.outcomes)
    items_succeeded = sum(outcome.inserted_count + outcome.skipped_count for outcome in result.outcomes)
    items_failed = max(items_processed - items_succeeded, 0)
    if items_failed == 0 and result.status is not FirehoseRunStatus.SUCCESS:
        items_failed = sum(1 for outcome in result.outcomes if outcome.error)

    failure_entries = [
        {
            "mode": outcome.mode,
            "page": outcome.page,
            "anchor_date": outcome.anchor_date,
            "error": outcome.error,
        }
        for outcome in result.outcomes
        if outcome.error
    ]
    error_summary = None
    error_context = None
    if result.status is not FirehoseRunStatus.SUCCESS:
        error_summary = failure_entries[0]["error"] if failure_entries else result.artifact_error
        error_summary = error_summary or f"firehose run ended with status {result.status.value}"
        error_context = _serialize_json(
            {
                "status": result.status,
                "artifact_error": result.artifact_error,
                "failures": failure_entries,
            }
        )

    return AgentRunMetrics(
        items_processed=items_processed,
        items_succeeded=items_succeeded,
        items_failed=items_failed,
        error_summary=error_summary,
        error_context=error_context,
        provider_name="github",
        model_name=None,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
    )


def _summarize_backfill_run(result: BackfillRunResult) -> AgentRunMetrics:
    items_processed = sum(outcome.fetched_count for outcome in result.outcomes)
    items_succeeded = sum(outcome.inserted_count + outcome.skipped_count for outcome in result.outcomes)
    items_failed = max(items_processed - items_succeeded, 0)
    if items_failed == 0 and result.status is not BackfillRunStatus.SUCCESS:
        items_failed = sum(1 for outcome in result.outcomes if outcome.error)

    failure_entries = [
        {
            "page": outcome.page,
            "window_start_date": outcome.window_start_date,
            "created_before_boundary": outcome.created_before_boundary,
            "error": outcome.error,
            "rate_limit_backoff_seconds": outcome.rate_limit_backoff_seconds,
        }
        for outcome in result.outcomes
        if outcome.error
    ]
    error_summary = None
    error_context = None
    if result.status is not BackfillRunStatus.SUCCESS:
        error_summary = failure_entries[0]["error"] if failure_entries else result.artifact_error
        error_summary = error_summary or f"backfill run ended with status {result.status.value}"
        error_context = _serialize_json(
            {
                "status": result.status,
                "artifact_error": result.artifact_error,
                "checkpoint": result.checkpoint,
                "failures": failure_entries,
            }
        )

    return AgentRunMetrics(
        items_processed=items_processed,
        items_succeeded=items_succeeded,
        items_failed=items_failed,
        error_summary=error_summary,
        error_context=error_context,
        provider_name="github",
        model_name=None,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
    )


def _summarize_bouncer_run(result: BouncerRunResult) -> AgentRunMetrics:
    items_processed = len(result.outcomes)
    # Both ACCEPTED and REJECTED are correct triage decisions — only outcomes with
    # an actual error (unexpected processing failure) count as failed items.
    items_succeeded = sum(1 for outcome in result.outcomes if outcome.error is None)
    items_failed = sum(1 for outcome in result.outcomes if outcome.error is not None)

    failure_entries = [
        {
            "github_repository_id": outcome.github_repository_id,
            "full_name": outcome.full_name,
            "error": outcome.error,
            "triage_status": outcome.triage_status,
        }
        for outcome in result.outcomes
        if outcome.error
    ]
    error_summary = None
    error_context = None
    if result.status is not BouncerRunStatus.SUCCESS:
        error_summary = failure_entries[0]["error"] if failure_entries else result.artifact_error
        error_summary = error_summary or f"bouncer run ended with status {result.status.value}"
        error_context = _serialize_json(
            {
                "status": result.status,
                "artifact_error": result.artifact_error,
                "failures": failure_entries,
            }
        )

    return AgentRunMetrics(
        items_processed=items_processed,
        items_succeeded=items_succeeded,
        items_failed=items_failed,
        error_summary=error_summary,
        error_context=error_context,
        provider_name="local-rules",
        model_name=None,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
    )


def _summarize_analyst_run(result: AnalystRunResult) -> AgentRunMetrics:
    items_processed = len(result.outcomes)
    items_succeeded = sum(
        1 for outcome in result.outcomes if outcome.analysis_status is RepositoryAnalysisStatus.COMPLETED
    )
    items_failed = items_processed - items_succeeded

    failure_entries = [
        {
            "github_repository_id": outcome.github_repository_id,
            "full_name": outcome.full_name,
            "failure_code": outcome.failure_code,
            "failure_message": outcome.failure_message,
        }
        for outcome in result.outcomes
        if outcome.analysis_status is not RepositoryAnalysisStatus.COMPLETED
    ]
    error_summary = None
    error_context = None
    if result.status is not AnalystRunStatus.SUCCESS:
        error_summary = failure_entries[0]["failure_message"] if failure_entries else result.artifact_error
        error_summary = error_summary or f"analyst run ended with status {result.status.value}"
        error_context = _serialize_json(
            {
                "status": result.status,
                "artifact_error": result.artifact_error,
                "failures": failure_entries,
            }
        )

    return AgentRunMetrics(
        items_processed=items_processed,
        items_succeeded=items_succeeded,
        items_failed=items_failed,
        error_summary=error_summary,
        error_context=error_context,
        provider_name=result.provider_name,
        model_name=result.model_name,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        total_tokens=result.total_tokens,
    )


def _summarize_combiner_run(result: CombinerRunResult) -> AgentRunMetrics:
    return AgentRunMetrics(
        items_processed=1 if result.run_id is not None else 0,
        items_succeeded=1 if result.status is CombinerRunStatus.SUCCESS and result.run_id is not None else 0,
        items_failed=1 if result.status is CombinerRunStatus.FAILED else 0,
        error_summary=result.error_message,
        error_context=_serialize_json(
            {
                "status": result.status,
                "provider_name": result.provider_name,
                "model_name": result.model_name,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
            }
        ) if result.error_message else None,
        provider_name=result.provider_name,
        model_name=result.model_name,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        total_tokens=result.total_tokens,
    )


def run_configured_combiner_job() -> CombinerRunResult:
    with Session(engine) as session:
        return _run_tracked_job(
            session=session,
            agent_name="combiner",
            runtime_dir=settings.runtime.runtime_dir,
            execute_job=lambda run_id: run_combiner_job(
                session=session,
                runtime_dir=settings.runtime.runtime_dir,
            ),
            summarize_run=_summarize_combiner_run,
            is_success=lambda result: result.status is CombinerRunStatus.SUCCESS,
            is_skipped=lambda result: result.status is CombinerRunStatus.SKIPPED_PAUSED,
            is_paused_skip=lambda result: result.status is CombinerRunStatus.SKIPPED_PAUSED,
            skipped_reason="combiner run skipped because shutdown was requested.",
        )


def _unexpected_exception_payload(exc: Exception) -> dict[str, object]:
    return {
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }


def _serialize_json(payload: object) -> str:
    return json.dumps(payload, default=_json_default, sort_keys=True)


def _json_default(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _log_firehose_interval_gate(next_firehose_delay: float) -> None:
    configured_interval = float(calculate_firehose_interval_seconds())
    if next_firehose_delay >= configured_interval > 0:
        logger.info(
            "Skipping immediate follow-up Firehose pass; next run remains gated by the configured %ds interval.",
            int(configured_interval),
        )


async def _run_bouncer_if_pending(
    *,
    stop_event: asyncio.Event,
    thread_stop: threading.Event,
) -> bool:
    if stop_event.is_set():
        return False

    with Session(engine) as session:
        if is_agent_paused(session, "bouncer"):
            return False

    try:
        if not has_pending_bouncer_work():
            return False
    except Exception:
        logger.exception("Unable to inspect pending Bouncer work. Skipping this pass.")
        return False

    try:
        bouncer_result = await asyncio.to_thread(
            run_configured_bouncer_job,
            should_stop=thread_stop.is_set,
        )
    except DuplicateActiveAgentRunError:
        logger.info("Skipping Bouncer pass because another Bouncer run is already active.")
        return False
    _log_bouncer_result(bouncer_result)
    return True


async def _run_analyst_if_pending(
    *,
    stop_event: asyncio.Event,
    thread_stop: threading.Event,
) -> bool:
    if stop_event.is_set():
        return False

    with Session(engine) as session:
        if is_agent_paused(session, "analyst"):
            return False

    try:
        if not has_pending_analyst_work():
            return False
    except Exception:
        logger.exception("Unable to inspect pending Analyst work. Skipping this pass.")
        return False

    try:
        analyst_result = await asyncio.to_thread(
            run_configured_analyst_job,
            should_stop=thread_stop.is_set,
        )
    except DuplicateActiveAgentRunError:
        logger.info("Skipping Analyst pass because another Analyst run is already active.")
        return False
    _log_analyst_result(analyst_result)
    return True


async def _run_combiner_if_pending(
    *,
    stop_event: asyncio.Event,
    thread_stop: threading.Event,
) -> bool:
    if stop_event.is_set():
        return False

    try:
        if not has_pending_combiner_work():
            return False
    except Exception:
        logger.exception("Unable to inspect pending Combiner work. Skipping this pass.")
        return False

    try:
        result = await asyncio.to_thread(run_configured_combiner_job)
    except DuplicateActiveAgentRunError:
        logger.info("Skipping Combiner pass because another Combiner run is already active.")
        return False
    _log_combiner_result(result)
    return True


async def _run_due_intake_jobs(
    *,
    due_jobs: list[str],
    thread_stop: threading.Event,
) -> dict[str, object]:
    async def _run_due_job_with_watchdog(job_name: str) -> object:
        job_stop = threading.Event()
        should_stop = lambda: thread_stop.is_set() or job_stop.is_set()
        timeout_seconds = (
            calculate_firehose_run_timeout_seconds()
            if job_name == "firehose"
            else calculate_backfill_run_timeout_seconds()
        )
        job_fn = run_configured_firehose_job if job_name == "firehose" else run_configured_backfill_job

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    job_fn,
                    sleep_fn=_interruptible_sleep_factory(job_stop),
                    should_stop=should_stop,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            job_stop.set()
            logger.error(
                "%s exceeded the watchdog timeout of %ss; continuing other intake work.",
                job_name.title(),
                int(timeout_seconds),
            )
            return IntakeJobTimeoutError(job_name, timeout_seconds)

    if not _supports_parallel_intake_lanes():
        results: dict[str, object] = {}
        for job_name in due_jobs:
            try:
                if job_name in ("firehose", "backfill"):
                    results[job_name] = await _run_due_job_with_watchdog(job_name)
            except Exception as exc:
                results[job_name] = exc
        return results

    tasks: dict[str, asyncio.Task[object]] = {}
    for job_name in due_jobs:
        if job_name in ("firehose", "backfill"):
            tasks[job_name] = asyncio.create_task(_run_due_job_with_watchdog(job_name))

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    return {
        job_name: result
        for job_name, result in zip(tasks.keys(), results, strict=False)
    }


def _supports_parallel_intake_lanes() -> bool:
    try:
        return engine.url.get_backend_name() != "sqlite"
    except Exception:
        return False


def _interruptible_sleep_factory(thread_stop: threading.Event) -> Callable[[int], None]:
    def _interruptible_sleep(seconds: int) -> None:
        """Pacing sleep that returns early when a shutdown signal is received."""
        thread_stop.wait(timeout=seconds)

    return _interruptible_sleep


def _worker_process_lock_path(runtime_dir: Path | None) -> Path:
    base_dir = runtime_dir if runtime_dir is not None else Path.cwd()
    return base_dir / "locks" / _WORKER_PROCESS_LOCK_FILENAME


def _read_worker_lock_holder_pid(lock_file) -> int | None:
    try:
        lock_file.seek(0)
        payload = json.loads(lock_file.read() or "{}")
    except (OSError, json.JSONDecodeError, TypeError):
        return None

    pid = payload.get("pid")
    return pid if isinstance(pid, int) else None


@contextlib.contextmanager
def _acquire_worker_process_lock(runtime_dir: Path | None):
    lock_path = _worker_process_lock_path(runtime_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WorkerAlreadyRunningError(
                lock_path,
                holder_pid=_read_worker_lock_holder_pid(lock_file),
            ) from exc

        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(
            _serialize_json(
                {
                    "pid": os.getpid(),
                    "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
            )
        )
        lock_file.flush()
        yield
    finally:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except OSError:
            logger.debug("Worker process lock could not be released cleanly.", exc_info=True)
        lock_file.close()


async def _run_worker_loop() -> None:
    logger.info("Starting Agentic-Workflow worker processes...")

    # Validate recovery state before starting work
    with Session(engine) as session:
        validate_startup_recovery(session)

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

    # Startup passes — gated by the same interval/resume logic used after boot so a
    # restart does not unconditionally rerun jobs that just completed.  Any fatal
    # failure stops the worker so the process supervisor can detect and restart it.
    try:
        startup_due_jobs: list[str] = []
        if should_run_firehose_startup():
            startup_due_jobs.append("firehose")
        else:
            logger.info(
                "Skipping startup Firehose pass; next run gated by the configured %ds interval.",
                calculate_firehose_interval_seconds(),
            )
        if not stop_event.is_set() and should_run_backfill_startup():
            startup_due_jobs.append("backfill")
        elif not stop_event.is_set():
            logger.info(
                "Skipping startup Backfill pass; next run gated by the configured %ds interval.",
                calculate_backfill_interval_seconds(),
            )
        if startup_due_jobs and not stop_event.is_set():
            startup_results = await _run_due_intake_jobs(
                due_jobs=startup_due_jobs,
                thread_stop=_thread_stop,
            )
            firehose_result = startup_results.get("firehose")
            if isinstance(firehose_result, FirehoseRunResult):
                _log_firehose_result(firehose_result)
            elif isinstance(firehose_result, IntakeJobTimeoutError):
                _log_intake_timeout(firehose_result)
            elif isinstance(firehose_result, DuplicateActiveAgentRunError):
                logger.info("Skipping startup Firehose pass because another Firehose run is already active.")
            elif isinstance(firehose_result, Exception):
                raise firehose_result

            backfill_result = startup_results.get("backfill")
            if isinstance(backfill_result, BackfillRunResult):
                _log_backfill_result(backfill_result)
            elif isinstance(backfill_result, IntakeJobTimeoutError):
                _log_intake_timeout(backfill_result)
            elif isinstance(backfill_result, DuplicateActiveAgentRunError):
                logger.info("Skipping startup Backfill pass because another Backfill run is already active.")
            elif isinstance(backfill_result, Exception):
                raise backfill_result
        if not stop_event.is_set():
            await _run_bouncer_if_pending(stop_event=stop_event, thread_stop=_thread_stop)
        if not stop_event.is_set():
            await _run_analyst_if_pending(stop_event=stop_event, thread_stop=_thread_stop)
        if not stop_event.is_set():
            await _run_combiner_if_pending(stop_event=stop_event, thread_stop=_thread_stop)
    except Exception:
        logger.exception("Startup ingestion pass failed. Exiting.")
        sys.exit(1)

    next_firehose_delay = seconds_until_next_firehose_run()
    next_backfill_delay = seconds_until_next_backfill_run()
    _log_firehose_interval_gate(next_firehose_delay)
    logger.info(
        "Worker running. Next Firehose run in %ds. Next Backfill run in %ds. Press Ctrl+C to stop.",
        int(next_firehose_delay),
        int(next_backfill_delay),
    )

    next_firehose_run_at = time.monotonic() + next_firehose_delay
    # Resume the existing interval if we skipped the startup run, otherwise start a new interval
    next_backfill_run_at = time.monotonic() + next_backfill_delay

    # Continuous interval loop — individual run failures are logged but do not
    # stop the worker; only an unhandled startup failure is fatal.
    combiner_check_interval = 10.0  # Check for new Combiner runs every 10 seconds
    next_combiner_check_at = time.monotonic() + combiner_check_interval

    while not stop_event.is_set():
        next_due_at = min(next_firehose_run_at, next_backfill_run_at, next_combiner_check_at)
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

        if due_jobs:
            intake_results = await _run_due_intake_jobs(
                due_jobs=due_jobs,
                thread_stop=_thread_stop,
            )

            firehose_result = intake_results.get("firehose")
            if isinstance(firehose_result, FirehoseRunResult):
                _log_firehose_result(firehose_result)
                if firehose_result.status is FirehoseRunStatus.SKIPPED_PAUSED:
                    next_firehose_run_at = time.monotonic() + calculate_paused_poll_seconds()
                elif firehose_result.status is FirehoseRunStatus.SUCCESS:
                    next_firehose_run_at = time.monotonic() + seconds_until_next_firehose_run()
                else:
                    next_firehose_run_at = time.monotonic() + calculate_firehose_interval_seconds()
            elif isinstance(firehose_result, IntakeJobTimeoutError):
                _log_intake_timeout(firehose_result)
                next_firehose_run_at = time.monotonic() + calculate_firehose_interval_seconds()
            elif isinstance(firehose_result, DuplicateActiveAgentRunError):
                logger.info("Skipping Firehose pass because another Firehose run is already active.")
                next_firehose_run_at = time.monotonic() + calculate_intake_pacing_seconds()
            elif isinstance(firehose_result, Exception):
                logger.exception("Firehose run failed. Continuing to next interval.", exc_info=firehose_result)
                next_firehose_run_at = time.monotonic() + calculate_firehose_interval_seconds()

            backfill_result = intake_results.get("backfill")
            if isinstance(backfill_result, BackfillRunResult):
                _log_backfill_result(backfill_result)
                if backfill_result.status is BackfillRunStatus.SKIPPED_PAUSED:
                    next_backfill_run_at = time.monotonic() + calculate_paused_poll_seconds()
                elif backfill_result.status is BackfillRunStatus.SUCCESS:
                    next_backfill_run_at = time.monotonic() + seconds_until_next_backfill_run()
                else:
                    next_backfill_run_at = time.monotonic() + calculate_backfill_interval_seconds()
            elif isinstance(backfill_result, IntakeJobTimeoutError):
                _log_intake_timeout(backfill_result)
                next_backfill_run_at = time.monotonic() + calculate_backfill_interval_seconds()
            elif isinstance(backfill_result, DuplicateActiveAgentRunError):
                logger.info("Skipping Backfill pass because another Backfill run is already active.")
                next_backfill_run_at = time.monotonic() + calculate_intake_pacing_seconds()
            elif isinstance(backfill_result, Exception):
                logger.exception("Backfill run failed. Continuing to next interval.", exc_info=backfill_result)
                next_backfill_run_at = time.monotonic() + calculate_backfill_interval_seconds()

        if due_jobs and not stop_event.is_set():
            await _run_bouncer_if_pending(stop_event=stop_event, thread_stop=_thread_stop)
        if due_jobs and not stop_event.is_set():
            await _run_analyst_if_pending(stop_event=stop_event, thread_stop=_thread_stop)

        # Check Combiner on its own schedule (every 10s) or after producer jobs
        if (now >= next_combiner_check_at or due_jobs) and not stop_event.is_set():
            await _run_combiner_if_pending(stop_event=stop_event, thread_stop=_thread_stop)
            next_combiner_check_at = time.monotonic() + combiner_check_interval

    logger.info("Worker shutdown complete.")


async def main():
    try:
        with _acquire_worker_process_lock(settings.runtime.runtime_dir):
            await _run_worker_loop()
    except WorkerAlreadyRunningError as exc:
        logger.warning("%s Duplicate worker launch skipped.", exc)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)

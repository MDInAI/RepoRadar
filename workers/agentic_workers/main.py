from __future__ import annotations

import asyncio
import json
import logging
import math
import signal
import sys
import threading
import time
import traceback
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Callable
from typing import TypeVar

from sqlalchemy import func
from sqlmodel import Session, select

from agentic_workers.core.db import engine
from agentic_workers.core.config import settings
from agentic_workers.core.events import (
    complete_agent_run as finalize_agent_run,
    fail_agent_run as record_failed_agent_run,
    mark_agent_run_skipped,
    start_agent_run,
)
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

# Configure root logger
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


_FIREHOSE_MODES = (FirehoseMode.NEW, FirehoseMode.TRENDING)
ResultT = TypeVar("ResultT")


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
    if settings.provider.backfill_interval_seconds <= 0:
        raise ValueError("backfill_interval_seconds must be greater than zero")

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
        return _run_tracked_job(
            session=session,
            agent_name="firehose",
            execute_job=lambda run_id: run_firehose_job(
                session=session,
                provider=provider,
                runtime_dir=settings.runtime.runtime_dir,
                pacing_seconds=calculate_firehose_pacing_seconds(),
                modes=_FIREHOSE_MODES,
                per_page=settings.provider.firehose_per_page,
                pages=settings.provider.firehose_pages,
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
    provider = GitHubFirehoseProvider(github_token=settings.github_provider_token_value)
    with Session(engine) as session:
        return _run_tracked_job(
            session=session,
            agent_name="backfill",
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
    provider = GitHubFirehoseProvider(github_token=settings.github_provider_token_value)
    api_key = settings.ANTHROPIC_API_KEY.get_secret_value() if settings.ANTHROPIC_API_KEY else None
    gemini_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None
    analysis_provider = create_analysis_provider(
        settings.ANALYST_PROVIDER,
        api_key,
        settings.ANALYST_MODEL_NAME,
        gemini_key,
        settings.GEMINI_BASE_URL,
        settings.GEMINI_MODEL_NAME
    )
    with Session(engine) as session:
        return _run_tracked_job(
            session=session,
            agent_name="analyst",
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
        pending_count = session.exec(
            select(func.count(RepositoryIntake.github_repository_id))
            .where(RepositoryIntake.triage_status == RepositoryTriageStatus.ACCEPTED)
            .where(RepositoryIntake.analysis_status != RepositoryAnalysisStatus.COMPLETED)
        ).one()
    return int(pending_count or 0) > 0


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


def _log_bouncer_result(result: BouncerRunResult) -> None:
    logger.info(
        "Bouncer run complete: status=%s outcomes=%d",
        result.status,
        len(result.outcomes),
    )
    if result.artifact_error:
        logger.warning("Bouncer runtime artifact write failed: %s", result.artifact_error)
    if result.status is not BouncerRunStatus.SUCCESS:
        logger.warning("Bouncer run completed with non-success status: %s", result.status)


def _log_analyst_result(result: AnalystRunResult) -> None:
    logger.info(
        "Analyst run complete: status=%s outcomes=%d",
        result.status,
        len(result.outcomes),
    )
    if result.artifact_error:
        logger.warning("Analyst runtime artifact write failed: %s", result.artifact_error)
    if result.status is not AnalystRunStatus.SUCCESS:
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

    try:
        if not has_pending_bouncer_work():
            return False
    except Exception:
        logger.exception("Unable to inspect pending Bouncer work. Skipping this pass.")
        return False

    bouncer_result = await asyncio.to_thread(
        run_configured_bouncer_job,
        should_stop=thread_stop.is_set,
    )
    _log_bouncer_result(bouncer_result)
    return True


async def _run_analyst_if_pending(
    *,
    stop_event: asyncio.Event,
    thread_stop: threading.Event,
) -> bool:
    if stop_event.is_set():
        return False

    try:
        if not has_pending_analyst_work():
            return False
    except Exception:
        logger.exception("Unable to inspect pending Analyst work. Skipping this pass.")
        return False

    analyst_result = await asyncio.to_thread(
        run_configured_analyst_job,
        should_stop=thread_stop.is_set,
    )
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

    result = await asyncio.to_thread(run_configured_combiner_job)
    _log_combiner_result(result)
    return True


async def main():
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

    def _interruptible_sleep(seconds: int) -> None:
        """Pacing sleep that returns early when a shutdown signal is received."""
        _thread_stop.wait(timeout=seconds)

    # Startup passes — gated by the same interval/resume logic used after boot so a
    # restart does not unconditionally rerun jobs that just completed.  Any fatal
    # failure stops the worker so the process supervisor can detect and restart it.
    try:
        firehose_ran_at_startup = False
        if should_run_firehose_startup():
            firehose_result = await asyncio.to_thread(
                run_configured_firehose_job,
                sleep_fn=_interruptible_sleep,
                should_stop=_thread_stop.is_set,
            )
            _log_firehose_result(firehose_result)
            firehose_ran_at_startup = True
        else:
            logger.info(
                "Skipping startup Firehose pass; next run gated by the configured %ds interval.",
                calculate_firehose_interval_seconds(),
            )
        if not stop_event.is_set() and should_run_backfill_startup():
            if firehose_ran_at_startup:
                await asyncio.to_thread(_interruptible_sleep, calculate_intake_pacing_seconds())
            backfill_result = await asyncio.to_thread(
                run_configured_backfill_job,
                sleep_fn=_interruptible_sleep,
                should_stop=_thread_stop.is_set,
            )
            _log_backfill_result(backfill_result)
        elif not stop_event.is_set():
            logger.info(
                "Skipping startup Backfill pass; next run gated by the configured %ds interval.",
                calculate_backfill_interval_seconds(),
            )
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
                    next_firehose_run_at = time.monotonic() + seconds_until_next_firehose_run()
                else:
                    backfill_result = await asyncio.to_thread(
                        run_configured_backfill_job,
                        sleep_fn=_interruptible_sleep,
                        should_stop=_thread_stop.is_set,
                    )
                    _log_backfill_result(backfill_result)
                    next_backfill_run_at = time.monotonic() + seconds_until_next_backfill_run()
            except Exception:
                logger.exception("%s run failed. Continuing to next interval.", job_name.title())
                if job_name == "firehose":
                    next_firehose_run_at = time.monotonic() + calculate_firehose_interval_seconds()
                else:
                    # In case of failure, keep the interval logic to retry later rather than immediately
                    next_backfill_run_at = time.monotonic() + calculate_backfill_interval_seconds()

            if index < len(due_jobs) - 1 and not stop_event.is_set():
                await asyncio.to_thread(_interruptible_sleep, calculate_intake_pacing_seconds())

        if due_jobs and not stop_event.is_set():
            await _run_bouncer_if_pending(stop_event=stop_event, thread_stop=_thread_stop)
        if due_jobs and not stop_event.is_set():
            await _run_analyst_if_pending(stop_event=stop_event, thread_stop=_thread_stop)

        # Check Combiner on its own schedule (every 10s) or after producer jobs
        if (now >= next_combiner_check_at or due_jobs) and not stop_event.is_set():
            await _run_combiner_if_pending(stop_event=stop_event, thread_stop=_thread_stop)
            next_combiner_check_at = time.monotonic() + combiner_check_interval

    logger.info("Worker shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)

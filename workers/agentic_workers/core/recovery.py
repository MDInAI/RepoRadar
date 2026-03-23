from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlmodel import Session, select

from agentic_workers.core.failure_detector import classify_github_runtime_error
from agentic_workers.storage.backend_models import (
    AgentRun,
    AgentRunStatus,
    AgentPauseState,
    EventSeverity,
    FailureClassification,
    RepositoryAnalysisStatus,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
    SystemEvent,
)
from agentic_workers.storage.backfill_progress import load_backfill_progress
from agentic_workers.storage.firehose_progress import load_firehose_progress

logger = logging.getLogger(__name__)
_WORKER_MANAGED_AGENTS = ("firehose", "backfill", "bouncer", "analyst", "combiner")


def validate_startup_recovery(session: Session) -> None:
    """Validate checkpoint and queue state consistency before resuming work."""
    _validate_checkpoint_consistency(session)
    _recover_stale_running_agent_runs(session)
    _reset_stale_in_progress_states(session)
    _auto_resume_transient_intake_pauses(session)
    _log_recovery_diagnostics(session)


def _validate_checkpoint_consistency(session: Session) -> None:
    """Check that checkpoint records have consistent state."""
    firehose_checkpoint = load_firehose_progress(session)
    if firehose_checkpoint and firehose_checkpoint.resume_required:
        if firehose_checkpoint.active_mode is None or firehose_checkpoint.next_page < 1:
            logger.warning(
                "Firehose checkpoint has resume_required=True but invalid state: "
                "mode=%s, next_page=%d",
                firehose_checkpoint.active_mode,
                firehose_checkpoint.next_page,
            )

    backfill_checkpoint = load_backfill_progress(session)
    if backfill_checkpoint and backfill_checkpoint.resume_required:
        if backfill_checkpoint.next_page < 1:
            logger.warning(
                "Backfill checkpoint has resume_required=True but invalid next_page=%d",
                backfill_checkpoint.next_page,
            )


def _reset_stale_in_progress_states(session: Session) -> None:
    """Reset stale in_progress states left by crashed workers."""
    stale_items = session.exec(
        select(RepositoryIntake).where(RepositoryIntake.queue_status == RepositoryQueueStatus.IN_PROGRESS)
    ).all()

    for item in stale_items:
        item.queue_status = RepositoryQueueStatus.PENDING
        session.add(item)
        logger.info(
            "Reset stale in_progress item to pending: %s (triage=%s, analysis=%s)",
            item.full_name,
            item.triage_status,
            item.analysis_status,
        )

    if stale_items:
        session.commit()


def _recover_stale_running_agent_runs(session: Session) -> None:
    """Mark any pre-existing worker-managed running rows as failed on fresh worker startup."""
    running_runs = session.exec(
        select(AgentRun)
        .where(AgentRun.status == AgentRunStatus.RUNNING)
        .where(AgentRun.agent_name.in_(_WORKER_MANAGED_AGENTS))
        .order_by(AgentRun.started_at.asc(), AgentRun.id.asc())
    ).all()
    if not running_runs:
        return

    recovered_at = datetime.now(timezone.utc)
    for run in running_runs:
        run.status = AgentRunStatus.FAILED
        run.completed_at = recovered_at
        run.duration_seconds = max((recovered_at - run.started_at).total_seconds(), 0.0)
        run.error_summary = "Recovered stale running job during worker startup."
        run.error_context = (
            "The previous worker process exited before recording a terminal state, "
            "so startup recovery marked this run as failed."
        )
        session.add(run)
        session.add(
            SystemEvent(
                event_type="worker_recovered",
                agent_name=run.agent_name,
                severity=EventSeverity.WARNING,
                message=(
                    f"Recovered stale active {run.agent_name} run from a previous worker process."
                ),
                context_json=json.dumps(
                    {
                        "action": "mark_stale_run_failed",
                        "agent_run_id": run.id,
                        "started_at": run.started_at.isoformat(),
                    },
                    sort_keys=True,
                ),
                agent_run_id=run.id,
                created_at=recovered_at,
            )
        )
        logger.warning(
            "Recovered stale active %s run %s during worker startup.",
            run.agent_name,
            run.id,
        )

    session.commit()


def _auto_resume_transient_intake_pauses(session: Session) -> None:
    """Clear stale intake pauses when the triggering failure is now recognized as transient."""
    paused_states = session.exec(
        select(AgentPauseState).where(AgentPauseState.is_paused == True)  # noqa: E712
    ).all()

    resumed_agents: list[str] = []
    now = datetime.now(timezone.utc)
    for pause_state in paused_states:
        if pause_state.agent_name not in {"firehose", "backfill"}:
            continue
        if pause_state.triggered_by_event_id is None:
            continue

        triggering_event = session.get(SystemEvent, pause_state.triggered_by_event_id)
        if triggering_event is None:
            continue

        effective_classification = _classify_intake_pause_trigger(triggering_event)
        if effective_classification is not FailureClassification.RETRYABLE:
            continue

        pause_state.is_paused = False
        pause_state.pause_reason = None
        pause_state.resume_condition = None
        pause_state.triggered_by_event_id = None
        pause_state.resumed_at = now
        pause_state.resumed_by = "auto"
        session.add(pause_state)

        session.add(
            SystemEvent(
                event_type="agent_resumed",
                agent_name=pause_state.agent_name,
                severity=EventSeverity.INFO,
                message=f"Agent '{pause_state.agent_name}' auto-resumed after transient GitHub failure recovery.",
                context_json=json.dumps(
                    {
                        "action": "auto_resume_transient_pause",
                        "triggering_event_id": triggering_event.id,
                        "triggering_event_type": triggering_event.event_type,
                        "reclassified_as": effective_classification.value,
                    },
                    sort_keys=True,
                ),
                agent_run_id=triggering_event.agent_run_id,
                created_at=now,
            )
        )
        resumed_agents.append(pause_state.agent_name)

    if resumed_agents:
        session.commit()
        logger.info(
            "Auto-resumed stale transient intake pauses for: %s",
            ", ".join(sorted(resumed_agents)),
        )


def _classify_intake_pause_trigger(event: SystemEvent) -> FailureClassification | None:
    """Re-evaluate intake pause triggers so stale timeout pauses can self-heal after restart."""
    if event.agent_name not in {"firehose", "backfill"}:
        return None
    if event.event_type not in {"repository_discovery_failed", "agent_paused"}:
        return event.failure_classification

    if event.failure_classification is FailureClassification.RETRYABLE:
        return FailureClassification.RETRYABLE
    if event.failure_classification is FailureClassification.RATE_LIMITED:
        return FailureClassification.RATE_LIMITED

    candidates = [event.message]
    if event.context_json:
        try:
            context = json.loads(event.context_json)
        except json.JSONDecodeError:
            context = None
        if isinstance(context, dict):
            error_text = context.get("error")
            if isinstance(error_text, str) and error_text.strip():
                candidates.append(error_text)

    for candidate in candidates:
        if not candidate:
            continue
        inferred = classify_github_runtime_error(RuntimeError(candidate))
        if inferred is FailureClassification.RETRYABLE:
            return inferred

    return event.failure_classification


def _log_recovery_diagnostics(session: Session) -> None:
    """Log recovery diagnostics showing which agents are resuming."""
    firehose_checkpoint = load_firehose_progress(session)
    backfill_checkpoint = load_backfill_progress(session)

    recovery_info = []
    if firehose_checkpoint and firehose_checkpoint.resume_required:
        recovery_info.append(f"Firehose will resume from page {firehose_checkpoint.next_page}")
        _record_recovery_event(
            session,
            agent_name="firehose",
            message=f"Firehose resuming from checkpoint at page {firehose_checkpoint.next_page}",
            context={"next_page": firehose_checkpoint.next_page, "mode": str(firehose_checkpoint.active_mode)},
        )

    if backfill_checkpoint and backfill_checkpoint.resume_required:
        recovery_info.append(f"Backfill will resume from page {backfill_checkpoint.next_page}")
        _record_recovery_event(
            session,
            agent_name="backfill",
            message=f"Backfill resuming from checkpoint at page {backfill_checkpoint.next_page}",
            context={"next_page": backfill_checkpoint.next_page},
        )

    if recovery_info:
        logger.info("Recovery diagnostics: %s", "; ".join(recovery_info))
    else:
        logger.info("No checkpoint recovery required; starting fresh")


def _record_recovery_event(
    session: Session,
    agent_name: str,
    message: str,
    context: dict[str, object],
) -> None:
    """Record a worker_recovered system event."""
    event = SystemEvent(
        event_type="worker_recovered",
        agent_name=agent_name,
        severity=EventSeverity.INFO,
        message=message,
        context_json=json.dumps(context, sort_keys=True),
        created_at=datetime.now(timezone.utc),
    )
    session.add(event)
    session.commit()

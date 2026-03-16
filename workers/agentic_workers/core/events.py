from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlmodel import Session
from sqlmodel import select

from agentic_workers.storage.backend_models import (
    AgentRun,
    AgentRunStatus,
    EventSeverity,
    FailureClassification,
    FailureSeverity,
    SystemEvent,
)


class DuplicateActiveAgentRunError(RuntimeError):
    def __init__(self, agent_name: str) -> None:
        super().__init__(f"Agent '{agent_name}' already has an active run.")
        self.agent_name = agent_name


def start_agent_run(session: Session, agent_name: str) -> int:
    try:
        _reconcile_stale_running_runs(session, agent_name)
        active_run = session.exec(
            select(AgentRun)
            .where(AgentRun.agent_name == agent_name)
            .where(AgentRun.status == AgentRunStatus.RUNNING)
            .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
        ).first()
        if active_run is not None:
            raise DuplicateActiveAgentRunError(agent_name)

        run = AgentRun(agent_name=agent_name, status=AgentRunStatus.RUNNING)
        session.add(run)
        session.flush()
        if run.id is None:
            raise RuntimeError(f"Agent run for {agent_name} did not receive an id.")

        _add_system_event(
            session,
            event_type="agent_started",
            agent_name=agent_name,
            severity=EventSeverity.INFO,
            message=f"{agent_name} run started.",
            context_json=None,
            agent_run_id=run.id,
        )
        session.commit()
        session.refresh(run)
    except Exception:
        session.rollback()
        raise

    return run.id


def _reconcile_stale_running_runs(session: Session, agent_name: str) -> None:
    stale_before = datetime.now(timezone.utc) - timedelta(minutes=10)
    running_runs = session.exec(
        select(AgentRun)
        .where(AgentRun.agent_name == agent_name)
        .where(AgentRun.status == AgentRunStatus.RUNNING)
        .where(AgentRun.started_at <= stale_before)
        .order_by(AgentRun.started_at.asc(), AgentRun.id.asc())
    ).all()
    if not running_runs:
        return

    recovered_at = datetime.now(timezone.utc)
    for run in running_runs:
        run.status = AgentRunStatus.FAILED
        run.completed_at = recovered_at
        run.duration_seconds = max((recovered_at - run.started_at).total_seconds(), 0.0)
        run.error_summary = "Recovered stale running job before a new run started."
        run.error_context = (
            "The worker recovered this run automatically because it remained running "
            "beyond the stale timeout window."
        )
        session.add(run)
    session.flush()


def complete_agent_run(
    session: Session,
    run_id: int,
    items_processed: int,
    items_succeeded: int,
    items_failed: int,
    provider_name: str | None = None,
    model_name: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
) -> None:
    _finish_existing_run(
        session,
        run_id=run_id,
        status=AgentRunStatus.COMPLETED,
        items_processed=items_processed,
        items_succeeded=items_succeeded,
        items_failed=items_failed,
        error_summary=None,
        error_context=None,
        provider_name=provider_name,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        event_type="agent_completed",
        severity=EventSeverity.INFO,
        message="{agent_name} run completed.",
        context_json=json.dumps(
            {
                "items_processed": items_processed,
                "items_succeeded": items_succeeded,
                "items_failed": items_failed,
            },
            sort_keys=True,
        ),
    )


def fail_agent_run(
    session: Session,
    run_id: int,
    error_summary: str,
    error_context: str | None,
    items_processed: int | None,
    items_succeeded: int | None,
    items_failed: int | None,
    provider_name: str | None = None,
    model_name: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
) -> None:
    _finish_existing_run(
        session,
        run_id=run_id,
        status=AgentRunStatus.FAILED,
        items_processed=items_processed,
        items_succeeded=items_succeeded,
        items_failed=items_failed,
        error_summary=error_summary,
        error_context=error_context,
        provider_name=provider_name,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        event_type="agent_failed",
        severity=EventSeverity.ERROR,
        message=error_summary,
        context_json=error_context,
    )


def mark_agent_run_skipped(
    session: Session,
    run_id: int,
    reason: str,
    *,
    status: AgentRunStatus = AgentRunStatus.SKIPPED,
    items_processed: int | None = 0,
    items_succeeded: int | None = 0,
    items_failed: int | None = 0,
    provider_name: str | None = None,
    model_name: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
) -> None:
    event_type = (
        "agent_skipped_paused"
        if status is AgentRunStatus.SKIPPED_PAUSED
        else "agent_skipped"
    )
    _finish_existing_run(
        session,
        run_id=run_id,
        status=status,
        items_processed=items_processed,
        items_succeeded=items_succeeded,
        items_failed=items_failed,
        error_summary=reason,
        error_context=None,
        provider_name=provider_name,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        event_type=event_type,
        severity=EventSeverity.INFO,
        message=reason,
        context_json=None,
    )


def skip_agent_run(session: Session, agent_name: str, reason: str) -> None:
    try:
        skipped_at = datetime.now(timezone.utc)
        run = AgentRun(
            agent_name=agent_name,
            status=AgentRunStatus.SKIPPED,
            started_at=skipped_at,
            completed_at=skipped_at,
            duration_seconds=0.0,
            items_processed=0,
            items_succeeded=0,
            items_failed=0,
            error_summary=reason,
            error_context=None,
            provider_name=None,
            model_name=None,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
        )
        session.add(run)
        session.flush()
        if run.id is None:
            raise RuntimeError(f"Skipped agent run for {agent_name} did not receive an id.")

        _add_system_event(
            session,
            event_type="agent_skipped",
            agent_name=agent_name,
            severity=EventSeverity.INFO,
            message=reason,
            context_json=None,
            agent_run_id=run.id,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise


def emit_event(
    session: Session,
    event_type: str,
    agent_name: str,
    severity: str | EventSeverity,
    message: str,
    context_json: str | None,
    agent_run_id: int | None,
) -> None:
    try:
        _add_system_event(
            session,
            event_type=event_type,
            agent_name=agent_name,
            severity=severity,
            message=message,
            context_json=context_json,
            agent_run_id=agent_run_id,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise


def emit_failure_event(
    session: Session,
    *,
    event_type: str,
    agent_name: str,
    message: str,
    classification: FailureClassification,
    failure_severity: FailureSeverity,
    http_status_code: int | None = None,
    retry_after_seconds: int | None = None,
    affected_repository_id: int | None = None,
    upstream_provider: str | None = None,
    context_json: str | None = None,
    agent_run_id: int | None = None,
    commit: bool = False,
) -> int:
    """Emit a SystemEvent enriched with structured failure classification context.

    Callers control the transaction by default so failure events can be committed
    atomically with the related pipeline-state update. If event creation fails,
    the exception propagates to the caller without rolling back, preserving any
    uncommitted state updates.

    Returns the event ID.
    """
    # Map FailureSeverity → EventSeverity for the general severity field
    _severity_map: dict[FailureSeverity, EventSeverity] = {
        FailureSeverity.WARNING: EventSeverity.WARNING,
        FailureSeverity.ERROR: EventSeverity.ERROR,
        FailureSeverity.CRITICAL: EventSeverity.CRITICAL,
    }
    event_severity = _severity_map[failure_severity]
    event = SystemEvent(
        event_type=event_type,
        agent_name=agent_name,
        severity=event_severity,
        message=message,
        context_json=context_json,
        agent_run_id=agent_run_id,
        failure_classification=classification,
        failure_severity=failure_severity,
        http_status_code=http_status_code,
        retry_after_seconds=retry_after_seconds,
        affected_repository_id=affected_repository_id,
        upstream_provider=upstream_provider,
    )
    session.add(event)
    if commit:
        session.commit()
    session.flush()
    return event.id


def pause_event_run_id(
    *,
    triggering_agent_name: str,
    affected_agent_name: str,
    triggering_run_id: int | None,
) -> int | None:
    if triggering_run_id is None:
        return None
    if affected_agent_name != triggering_agent_name:
        return None
    return triggering_run_id


def _add_system_event(
    session: Session,
    *,
    event_type: str,
    agent_name: str,
    severity: str | EventSeverity,
    message: str,
    context_json: str | None,
    agent_run_id: int | None,
) -> None:
    event = SystemEvent(
        event_type=event_type,
        agent_name=agent_name,
        severity=_coerce_severity(severity),
        message=message,
        context_json=context_json,
        agent_run_id=agent_run_id,
    )
    session.add(event)


def _finish_existing_run(
    session: Session,
    *,
    run_id: int,
    status: AgentRunStatus,
    items_processed: int | None,
    items_succeeded: int | None,
    items_failed: int | None,
    error_summary: str | None,
    error_context: str | None,
    provider_name: str | None,
    model_name: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    event_type: str,
    severity: EventSeverity,
    message: str,
    context_json: str | None,
) -> None:
    try:
        run = _require_run(session, run_id)
        completed_at = datetime.now(timezone.utc)
        run.status = status
        run.completed_at = completed_at
        run.duration_seconds = max((completed_at - run.started_at).total_seconds(), 0.0)
        run.items_processed = items_processed
        run.items_succeeded = items_succeeded
        run.items_failed = items_failed
        run.error_summary = error_summary
        run.error_context = error_context
        run.provider_name = provider_name
        run.model_name = model_name
        run.input_tokens = input_tokens
        run.output_tokens = output_tokens
        run.total_tokens = total_tokens
        session.add(run)

        _add_system_event(
            session,
            event_type=event_type,
            agent_name=run.agent_name,
            severity=severity,
            message=message.replace("{agent_name}", run.agent_name),
            context_json=context_json,
            agent_run_id=run_id,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise


def _require_run(session: Session, run_id: int) -> AgentRun:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise ValueError(f"Agent run {run_id} was not found.")
    return run


def _coerce_severity(severity: str | EventSeverity) -> EventSeverity:
    if isinstance(severity, EventSeverity):
        return severity
    return EventSeverity(severity)

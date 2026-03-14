from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlmodel import Session, select

from agentic_workers.storage.backend_models import (
    EventSeverity,
    RepositoryAnalysisStatus,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
    SystemEvent,
)
from agentic_workers.storage.backfill_progress import load_backfill_progress
from agentic_workers.storage.firehose_progress import load_firehose_progress

logger = logging.getLogger(__name__)


def validate_startup_recovery(session: Session) -> None:
    """Validate checkpoint and queue state consistency before resuming work."""
    _validate_checkpoint_consistency(session)
    _reset_stale_in_progress_states(session)
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
    import json

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

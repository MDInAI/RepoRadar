from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
import logging
import re
from pathlib import Path
from typing import Callable

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, select

from agentic_workers.core.events import emit_failure_event
from agentic_workers.core.failure_detector import determine_severity
from agentic_workers.core.pause_manager import execute_pause, is_agent_paused
from agentic_workers.core.pause_policy import evaluate_pause_policy
from agentic_workers.storage.backend_models import (
    FailureClassification,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageExplanation,
    RepositoryTriageExplanationKind,
    RepositoryTriageStatus,
)
from agentic_workers.storage.agent_progress_snapshots import write_agent_progress_snapshot

logger = logging.getLogger(__name__)


class BouncerRunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"
    SKIPPED = "skipped"
    SKIPPED_PAUSED = "skipped_paused"


@dataclass(frozen=True, slots=True)
class BouncerDecision:
    triage_status: RepositoryTriageStatus
    explanation_kind: RepositoryTriageExplanationKind
    explanation_summary: str
    matched_include_rules: tuple[str, ...]
    matched_exclude_rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BouncerRepositoryOutcome:
    github_repository_id: int
    full_name: str
    triage_status: RepositoryTriageStatus | None
    queue_status: RepositoryQueueStatus
    explanation_kind: RepositoryTriageExplanationKind | None
    explanation_summary: str | None
    explained_at: datetime | None
    matched_include_rules: tuple[str, ...]
    matched_exclude_rules: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BouncerRunResult:
    status: BouncerRunStatus
    outcomes: list[BouncerRepositoryOutcome]
    artifact_path: Path | None
    artifact_error: str | None = None


ArtifactWriter = Callable[..., Path | None]


def run_bouncer_job(
    *,
    session: Session,
    runtime_dir: Path | None,
    include_rules: tuple[str, ...] = (),
    exclude_rules: tuple[str, ...] = (),
    should_stop: Callable[[], bool] | None = None,
    write_artifact: ArtifactWriter | None = None,
    agent_run_id: int | None = None,
) -> BouncerRunResult:
    # Check if agent is paused
    if is_agent_paused(session, "bouncer"):
        logger.info("Bouncer is paused, skipping run")
        return BouncerRunResult(
            status=BouncerRunStatus.SKIPPED_PAUSED,
            outcomes=[],
            artifact_path=None,
        )

    normalized_include_rules = _normalize_rules(include_rules)
    normalized_exclude_rules = _normalize_rules(exclude_rules)
    artifact_writer = write_artifact or _write_run_artifact

    queue_rows = session.exec(
        select(RepositoryIntake)
        .where(RepositoryIntake.queue_status == RepositoryQueueStatus.PENDING)
        .where(RepositoryIntake.triage_status == RepositoryTriageStatus.PENDING)
        .order_by(RepositoryIntake.queue_created_at, RepositoryIntake.github_repository_id)
    ).all()

    outcomes: list[BouncerRepositoryOutcome] = []
    interrupted = False
    total_items = len(queue_rows)
    _write_bouncer_progress_snapshot(
        runtime_dir=runtime_dir,
        total_items=total_items,
        outcomes=outcomes,
        current_target=queue_rows[0].full_name if queue_rows else None,
        current_activity="Preparing pending repositories for triage.",
    )
    for row in queue_rows:
        if should_stop is not None and should_stop():
            interrupted = True
            break

        _write_bouncer_progress_snapshot(
            runtime_dir=runtime_dir,
            total_items=total_items,
            outcomes=outcomes,
            current_target=row.full_name,
            current_activity="Evaluating repository triage rules.",
        )

        started_at = datetime.now(timezone.utc)
        try:
            row.queue_status = RepositoryQueueStatus.IN_PROGRESS
            row.processing_started_at = row.processing_started_at or started_at
            row.status_updated_at = started_at

            decision = evaluate_repository(
                full_name=row.full_name,
                description=row.repository_description,
                include_rules=normalized_include_rules,
                exclude_rules=normalized_exclude_rules,
            )

            completed_at = datetime.now(timezone.utc)
            row.queue_status = RepositoryQueueStatus.COMPLETED
            row.triage_status = decision.triage_status
            row.triaged_at = completed_at
            row.processing_completed_at = completed_at
            row.status_updated_at = completed_at
            _upsert_triage_explanation(
                session,
                github_repository_id=row.github_repository_id,
                decision=decision,
                explained_at=completed_at,
            )
            session.add(row)
            session.commit()
            outcomes.append(
                BouncerRepositoryOutcome(
                    github_repository_id=row.github_repository_id,
                    full_name=row.full_name,
                    triage_status=decision.triage_status,
                    queue_status=row.queue_status,
                    explanation_kind=decision.explanation_kind,
                    explanation_summary=decision.explanation_summary,
                    explained_at=completed_at,
                    matched_include_rules=decision.matched_include_rules,
                    matched_exclude_rules=decision.matched_exclude_rules,
                )
            )
            _write_bouncer_progress_snapshot(
                runtime_dir=runtime_dir,
                total_items=total_items,
                outcomes=outcomes,
                current_target=row.full_name,
                current_activity="Persisted triage decision.",
            )
        except Exception as exc:
            rollback_error = _rollback_after_failure(session)
            failed_at = datetime.now(timezone.utc)
            recovery_error = _mark_repository_failed(
                session=session,
                github_repository_id=row.github_repository_id,
                started_at=started_at,
                failed_at=failed_at,
                commit=True,
            )
            if recovery_error is None:
                try:
                    classification = FailureClassification.BLOCKING
                    failure_sev = determine_severity(classification, 1)
                    event_id = emit_failure_event(
                        session,
                        event_type="repository_triage_failed",
                        agent_name="bouncer",
                        message="bouncer failed while evaluating repository rules.",
                        classification=classification,
                        failure_severity=failure_sev,
                        affected_repository_id=row.github_repository_id,
                        context_json=json.dumps(
                            {
                                "github_repository_id": row.github_repository_id,
                                "full_name": row.full_name,
                                "error": str(exc),
                            },
                            sort_keys=True,
                        ),
                        agent_run_id=agent_run_id,
                    )
                    decision = evaluate_pause_policy("bouncer", classification, failure_sev, 1)
                    if decision.should_pause:
                        execute_pause(session, decision, event_id)
                        pause_context = json.dumps({
                            "pause_reason": decision.reason,
                            "resume_condition": decision.resume_condition,
                            "is_paused": True,
                        })
                        emit_failure_event(
                            session,
                            event_type="agent_paused",
                            agent_name="bouncer",
                            message=f"bouncer paused: {decision.reason}",
                            classification=classification,
                            failure_severity="critical",
                            context_json=pause_context,
                            agent_run_id=agent_run_id,
                        )
                    session.commit()
                except Exception:
                    session.rollback()
                    logger.warning(
                        "Failed to emit repository_triage_failed event for %s",
                        row.full_name,
                        exc_info=True,
                    )
            outcomes.append(
                BouncerRepositoryOutcome(
                    github_repository_id=row.github_repository_id,
                    full_name=row.full_name,
                    triage_status=None,
                    queue_status=RepositoryQueueStatus.FAILED,
                    explanation_kind=None,
                    explanation_summary=None,
                    explained_at=None,
                    matched_include_rules=(),
                    matched_exclude_rules=(),
                    error=_format_failure_error(
                        exc,
                        rollback_error=rollback_error,
                        recovery_error=recovery_error,
                    ),
                )
            )
            _write_bouncer_progress_snapshot(
                runtime_dir=runtime_dir,
                total_items=total_items,
                outcomes=outcomes,
                current_target=row.full_name,
                current_activity="Recorded triage failure.",
            )

    status = _determine_status(
        outcomes,
        interrupted=interrupted,
    )
    artifact_path: Path | None = None
    artifact_error: str | None = None
    try:
        artifact_path = artifact_writer(
            runtime_dir=runtime_dir,
            status=status,
            outcomes=outcomes,
            include_rules=normalized_include_rules,
            exclude_rules=normalized_exclude_rules,
        )
    except OSError as exc:
        artifact_error = str(exc)
        if status is BouncerRunStatus.SUCCESS:
            status = BouncerRunStatus.PARTIAL_FAILURE

    _write_bouncer_progress_snapshot(
        runtime_dir=runtime_dir,
        total_items=total_items,
        outcomes=outcomes,
        current_target=None,
        current_activity=(
            "Bouncer run completed."
            if status is BouncerRunStatus.SUCCESS
            else "Bouncer run finished with warnings or failures."
        ),
        status_label=status.value.replace("_", " "),
    )

    return BouncerRunResult(
        status=status,
        outcomes=outcomes,
        artifact_path=artifact_path,
        artifact_error=artifact_error,
    )


def _write_bouncer_progress_snapshot(
    *,
    runtime_dir: Path | None,
    total_items: int,
    outcomes: list[BouncerRepositoryOutcome],
    current_target: str | None,
    current_activity: str,
    status_label: str = "running",
) -> None:
    completed_count = len(outcomes)
    failed_count = sum(1 for outcome in outcomes if outcome.error is not None)
    progress_percent = int(round((completed_count / total_items) * 100)) if total_items > 0 else None
    try:
        write_agent_progress_snapshot(
            runtime_dir=runtime_dir,
            agent_name="bouncer",
            payload={
                "status_label": status_label,
                "current_activity": current_activity,
                "current_target": current_target,
                "completed_count": completed_count,
                "total_count": total_items,
                "remaining_count": max(total_items - completed_count, 0),
                "progress_percent": progress_percent,
                "unit_label": "repos",
                "source": "triage queue snapshot",
                "details": [
                    f"Completed decisions: {completed_count}",
                    f"Failed decisions: {failed_count}",
                ],
            },
        )
    except OSError:
        logger.warning("Failed to write bouncer progress snapshot", exc_info=True)


def evaluate_repository(
    *,
    full_name: str,
    description: str | None,
    include_rules: tuple[str, ...],
    exclude_rules: tuple[str, ...],
) -> BouncerDecision:
    haystack = _normalized_haystack(full_name=full_name, description=description)
    
    def _matches_rule(rule: str, text: str) -> bool:
        # Use word boundaries so "saas" doesn't match "isaas"
        escaped = re.escape(rule)
        return bool(re.search(rf"\b{escaped}\b", text))

    matched_exclude_rules = tuple(rule for rule in exclude_rules if _matches_rule(rule, haystack))
    matched_include_rules = tuple(rule for rule in include_rules if _matches_rule(rule, haystack))

    if matched_exclude_rules:
        return BouncerDecision(
            triage_status=RepositoryTriageStatus.REJECTED,
            explanation_kind=RepositoryTriageExplanationKind.EXCLUDE_RULE,
            explanation_summary=_summarize_rule_match(
                "Rejected because exclude rules matched",
                matched_exclude_rules,
            ),
            matched_include_rules=matched_include_rules,
            matched_exclude_rules=matched_exclude_rules,
        )
    if include_rules and not matched_include_rules:
        return BouncerDecision(
            triage_status=RepositoryTriageStatus.REJECTED,
            explanation_kind=RepositoryTriageExplanationKind.ALLOWLIST_MISS,
            explanation_summary=(
                "Rejected because no include rules matched the configured allowlist."
            ),
            matched_include_rules=(),
            matched_exclude_rules=(),
        )
    return BouncerDecision(
        triage_status=RepositoryTriageStatus.ACCEPTED,
        explanation_kind=(
            RepositoryTriageExplanationKind.INCLUDE_RULE
            if matched_include_rules
            else RepositoryTriageExplanationKind.PASS_THROUGH
        ),
        explanation_summary=(
            _summarize_rule_match(
                "Accepted because include rules matched",
                matched_include_rules,
            )
            if matched_include_rules
            else "Accepted because no include allowlist is configured and no exclude rules matched."
        ),
        matched_include_rules=matched_include_rules,
        matched_exclude_rules=(),
    )


def _normalize_rules(rules: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(rule.strip().lower() for rule in rules if rule.strip())


def _normalized_haystack(*, full_name: str, description: str | None) -> str:
    return "\n".join(
        part.lower()
        for part in (full_name, description or "")
        if part
    ).strip()


def _determine_status(
    outcomes: list[BouncerRepositoryOutcome],
    *,
    interrupted: bool = False,
) -> BouncerRunStatus:
    has_error = any(outcome.error for outcome in outcomes)
    if interrupted and not has_error:
        return BouncerRunStatus.SKIPPED
    has_success = any(outcome.error is None for outcome in outcomes)
    if has_error and has_success:
        return BouncerRunStatus.PARTIAL_FAILURE
    if has_error:
        return BouncerRunStatus.FAILED
    return BouncerRunStatus.SUCCESS


def _summarize_rule_match(prefix: str, rules: tuple[str, ...]) -> str:
    return f"{prefix}: {', '.join(rules)}."


def _upsert_triage_explanation(
    session: Session,
    *,
    github_repository_id: int,
    decision: BouncerDecision,
    explained_at: datetime,
) -> None:
    values = {
        "github_repository_id": github_repository_id,
        "explanation_kind": decision.explanation_kind,
        "explanation_summary": decision.explanation_summary,
        "matched_include_rules": list(decision.matched_include_rules),
        "matched_exclude_rules": list(decision.matched_exclude_rules),
        "explained_at": explained_at,
    }
    update_values = {
        key: value
        for key, value in values.items()
        if key != "github_repository_id"
    }
    table = RepositoryTriageExplanation.__table__
    dialect_name = session.get_bind().dialect.name

    if dialect_name == "sqlite":
        statement = sqlite_insert(table).values(**values)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[table.c.github_repository_id],
                set_=update_values,
            )
        )
        return

    if dialect_name == "postgresql":
        statement = postgresql_insert(table).values(**values)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[table.c.github_repository_id],
                set_=update_values,
            )
        )
        return

    explanation = session.get(RepositoryTriageExplanation, github_repository_id)
    if explanation is None:
        explanation = RepositoryTriageExplanation(**values)
    else:
        explanation.explanation_kind = decision.explanation_kind
        explanation.explanation_summary = decision.explanation_summary
        explanation.matched_include_rules = list(decision.matched_include_rules)
        explanation.matched_exclude_rules = list(decision.matched_exclude_rules)
        explanation.explained_at = explained_at
    session.add(explanation)


def _rollback_after_failure(session: Session) -> str | None:
    try:
        session.rollback()
    except Exception as exc:
        return f"rollback failed: {exc}"
    return None


def _mark_repository_failed(
    *,
    session: Session,
    github_repository_id: int,
    started_at: datetime,
    failed_at: datetime,
    commit: bool = True,
) -> str | None:
    try:
        failed_row = session.get(RepositoryIntake, github_repository_id)
        if failed_row is None:
            return "failure status update skipped: repository row could not be reloaded"
        failed_row.queue_status = RepositoryQueueStatus.FAILED
        failed_row.processing_started_at = failed_row.processing_started_at or started_at
        failed_row.last_failed_at = failed_at
        failed_row.status_updated_at = failed_at
        session.add(failed_row)
        if commit:
            session.commit()
    except Exception as exc:
        _rollback_after_failure(session)
        return f"failure status update skipped: {exc}"
    return None


def _format_failure_error(
    error: Exception,
    *,
    rollback_error: str | None,
    recovery_error: str | None,
) -> str:
    messages = [str(error)]
    if rollback_error is not None:
        messages.append(rollback_error)
    if recovery_error is not None:
        messages.append(recovery_error)
    return " | ".join(messages)


def _write_run_artifact(
    *,
    runtime_dir: Path | None,
    status: BouncerRunStatus,
    outcomes: list[BouncerRepositoryOutcome],
    include_rules: tuple[str, ...],
    exclude_rules: tuple[str, ...],
) -> Path | None:
    if runtime_dir is None:
        return None

    artifact_dir = runtime_dir / "bouncer" / "triage-runs"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    artifact_path = artifact_dir / f"{timestamp}.json"
    artifact_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": status.value,
                "include_rules": list(include_rules),
                "exclude_rules": list(exclude_rules),
                "summary": {
                    "accepted": sum(
                        outcome.triage_status is RepositoryTriageStatus.ACCEPTED
                        for outcome in outcomes
                    ),
                    "rejected": sum(
                        outcome.triage_status is RepositoryTriageStatus.REJECTED
                        for outcome in outcomes
                    ),
                    "failed": sum(outcome.error is not None for outcome in outcomes),
                },
                "outcomes": [
                    {
                        "github_repository_id": outcome.github_repository_id,
                        "full_name": outcome.full_name,
                        "triage_status": (
                            outcome.triage_status.value
                            if outcome.triage_status is not None
                            else None
                        ),
                        "queue_status": outcome.queue_status.value,
                        "explanation_kind": (
                            outcome.explanation_kind.value
                            if outcome.explanation_kind is not None
                            else None
                        ),
                        "explanation_summary": outcome.explanation_summary,
                        "explained_at": (
                            outcome.explained_at.isoformat()
                            if outcome.explained_at is not None
                            else None
                        ),
                        "matched_include_rules": list(outcome.matched_include_rules),
                        "matched_exclude_rules": list(outcome.matched_exclude_rules),
                        "error": outcome.error,
                    }
                    for outcome in outcomes
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return artifact_path

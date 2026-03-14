from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from app.core.event_broadcaster import EventBroadcaster
from app.core.errors import AppError
from app.repositories.agent_event_repository import (
    AgentEventRepository,
    AgentRunListFilters,
    FailureEventListFilters,
    IncidentListFilters,
    SystemEventListFilters,
)
from app.models import AGENT_NAMES, AgentRunStatus, EventSeverity

if TYPE_CHECKING:
    from app.schemas.incident import IncidentListParams, IncidentResponse
from app.schemas.agent_event import (
    AgentLatestRunsResponse,
    AgentPauseStateResponse,
    AgentRunDetailResponse,
    AgentRunListParams,
    AgentRunResponse,
    AgentStatusEntry,
    FailureEventListParams,
    SystemEventListParams,
    SystemEventResponse,
)


_AGENT_RUN_EVENT_TYPES = {
    AgentRunStatus.RUNNING: "agent.run_started",
    AgentRunStatus.COMPLETED: "agent.run_completed",
    AgentRunStatus.FAILED: "agent.run_failed",
    AgentRunStatus.SKIPPED: "agent.run_skipped",
    AgentRunStatus.SKIPPED_PAUSED: "agent.run_skipped_paused",
}
_SYSTEM_EVENT_TO_AGENT_EVENT_TYPE = {
    "agent_started": "agent.run_started",
    "agent_completed": "agent.run_completed",
    "agent_failed": "agent.run_failed",
    "agent_skipped": "agent.run_skipped",
    "agent_skipped_paused": "agent.run_skipped_paused",
}

logger = logging.getLogger(__name__)


class AgentEventService:
    def __init__(
        self,
        repository: AgentEventRepository,
        broadcaster: EventBroadcaster | None = None,
    ) -> None:
        self.repository = repository
        self.broadcaster = broadcaster

    def list_agent_runs(self, params: AgentRunListParams) -> list[AgentRunResponse]:
        return [
            self._build_agent_run_response(record)
            for record in self.repository.list_agent_runs(
                AgentRunListFilters(
                    agent_name=params.agent_name,
                    status=params.status,
                    since=params.since,
                    until=params.until,
                    limit=params.limit,
                )
            )
        ]

    def get_latest_run_per_agent(self) -> AgentLatestRunsResponse:
        runs_by_name = {
            record.agent_name: self._build_agent_run_response(record)
            for record in self.repository.get_latest_run_per_agent()
        }
        return AgentLatestRunsResponse(
            agents=[
                AgentStatusEntry(
                    agent_name=name,
                    has_run=name in runs_by_name,
                    latest_run=runs_by_name.get(name),
                )
                for name in AGENT_NAMES
            ]
        )

    def get_agent_run_detail(self, run_id: int) -> AgentRunDetailResponse:
        record = self.repository.get_agent_run(run_id)
        if record is None:
            raise AppError(
                message=f"Agent run {run_id} was not found.",
                code="agent_run_not_found",
                status_code=404,
                details={"run_id": run_id},
            )

        return AgentRunDetailResponse(
            **self._build_agent_run_response(record).model_dump(),
            error_context=record.error_context,
            events=[
                self._build_system_event_response(event)
                for event in self.repository.list_events_for_run(run_id)
            ],
        )

    def list_system_events(self, params: SystemEventListParams) -> list[SystemEventResponse]:
        return [
            self._build_system_event_response(record)
            for record in self.repository.list_system_events(
                SystemEventListFilters(
                    agent_name=params.agent_name,
                    event_type=params.event_type,
                    severity=params.severity,
                    since=params.since,
                    until=params.until,
                    limit=params.limit,
                )
            )
        ]

    def list_failure_events(self, params: FailureEventListParams) -> list[SystemEventResponse]:
        return [
            self._build_system_event_response(record)
            for record in self.repository.list_failure_events(
                FailureEventListFilters(
                    agent_name=params.agent_name,
                    classification=params.classification,
                    severity=params.severity,
                    since=params.since,
                    limit=params.limit,
                )
            )
        ]

    def create_agent_run(self, agent_name: str) -> AgentRunResponse:
        record = self.repository.create_agent_run(agent_name)
        response = self._build_agent_run_response(record)
        self._broadcast_agent_run_update(response)
        return response

    def complete_agent_run(
        self,
        run_id: int,
        status: AgentRunStatus,
        items_processed: int | None,
        items_succeeded: int | None,
        items_failed: int | None,
        error_summary: str | None,
        error_context: str | None,
    ) -> AgentRunResponse:
        record = self.repository.complete_agent_run(
            run_id,
            status=status,
            items_processed=items_processed,
            items_succeeded=items_succeeded,
            items_failed=items_failed,
            error_summary=error_summary,
            error_context=error_context,
        )
        response = self._build_agent_run_response(record)
        self._broadcast_agent_run_update(response)
        return response

    def create_system_event(
        self,
        event_type: str,
        agent_name: str,
        severity: EventSeverity,
        message: str,
        context_json: str | None,
        agent_run_id: int | None,
    ) -> SystemEventResponse:
        record = self.repository.create_system_event(
            event_type=event_type,
            agent_name=agent_name,
            severity=severity,
            message=message,
            context_json=context_json,
            agent_run_id=agent_run_id,
        )
        response = self._build_system_event_response(record)
        self._broadcast_system_event(response)
        return response

    def get_latest_system_event_id(self) -> int | None:
        return self.repository.get_latest_system_event_id()

    def bridge_new_events(self, after_event_id: int | None, limit: int = 100) -> int | None:
        latest_event_id = after_event_id
        for record in self.repository.list_system_events_since(after_event_id, limit=limit):
            response = self._build_system_event_response(record)
            self._broadcast_system_event(response)

            agent_event_type = _SYSTEM_EVENT_TO_AGENT_EVENT_TYPE.get(record.event_type)
            if agent_event_type is not None and record.agent_run_id is not None:
                run = self.repository.get_agent_run(record.agent_run_id)
                if run is not None:
                    self._broadcast_agent_run_update(
                        self._build_agent_run_response(run),
                        event_type=agent_event_type,
                    )

            latest_event_id = record.id

        return latest_event_id

    @staticmethod
    def _build_agent_run_response(record: object) -> AgentRunResponse:
        return AgentRunResponse.model_validate(record)

    @staticmethod
    def _build_system_event_response(record: object) -> SystemEventResponse:
        return SystemEventResponse.model_validate(record)

    def _broadcast_agent_run_update(
        self,
        response: AgentRunResponse,
        event_type: str | None = None,
    ) -> None:
        if self.broadcaster is None:
            return
        self.broadcaster.broadcast(
            event_type or _AGENT_RUN_EVENT_TYPES[response.status],
            self._model_dump(response),
        )

    def _broadcast_system_event(self, response: SystemEventResponse) -> None:
        if self.broadcaster is None:
            return
        self.broadcaster.broadcast("system.event", self._model_dump(response))

    @staticmethod
    def _model_dump(model: AgentRunResponse | SystemEventResponse) -> dict[str, object]:
        return dict(model.model_dump(mode="json"))

    def list_agent_pause_states(self) -> list[AgentPauseStateResponse]:
        states = self.repository.list_agent_pause_states()
        return [AgentPauseStateResponse.model_validate(state) for state in states]

    def get_agent_pause_state(self, agent_name: str) -> AgentPauseStateResponse | None:
        state = self.repository.get_agent_pause_state(agent_name)
        if state is not None:
            return AgentPauseStateResponse.model_validate(state)
        # Return a synthetic unpaused response for known agents that have never been paused.
        # Unknown agent names still return None so the caller can 404.
        if agent_name in AGENT_NAMES:
            return AgentPauseStateResponse(agent_name=agent_name, is_paused=False)
        return None

    def resume_agent(self, agent_name: str) -> AgentPauseStateResponse:
        from datetime import datetime, timezone
        from app.models import ResumedBy

        # Validate agent name
        if agent_name not in AGENT_NAMES:
            raise AppError(
                message=f"Agent '{agent_name}' is not a recognised agent name.",
                code="agent_not_found",
                status_code=404,
            )

        # Get current pause state
        pause_state = self.repository.get_agent_pause_state(agent_name)
        if pause_state is None or not pause_state.is_paused:
            raise AppError(
                message=f"Agent '{agent_name}' is not currently paused.",
                code="agent_not_paused",
                status_code=409,
            )

        # Validate recovery source exists and cache checkpoint data
        cached_checkpoint = self._validate_recovery_source(agent_name, pause_state)

        # Clear pause state and record event in transaction
        try:
            pause_state.is_paused = False
            pause_state.resumed_at = datetime.now(timezone.utc)
            pause_state.resumed_by = ResumedBy.OPERATOR

            updated_state = self.repository.update_agent_pause_state(pause_state)

            # Record agent_resumed event (reuse cached checkpoint)
            recovery_context = self._build_recovery_context(agent_name, cached_checkpoint)
            self.repository.create_system_event(
                event_type="agent_resumed",
                agent_name=agent_name,
                severity=EventSeverity.INFO,
                message=f"Agent '{agent_name}' resumed by operator",
                context_json=json.dumps(recovery_context),
                agent_run_id=None,
            )
        except Exception:
            # Rollback on any failure
            self.repository.session.rollback()
            raise

        # Broadcast pause state change
        response = AgentPauseStateResponse.model_validate(updated_state)
        if self.broadcaster:
            self.broadcaster.broadcast("agent.resumed", self._model_dump_pause_state(response))

        return response

    def pause_agent(self, agent_name: str, pause_reason: str, resume_condition: str) -> AgentPauseStateResponse:
        from datetime import datetime, timezone

        if agent_name not in AGENT_NAMES:
            raise AppError(
                message=f"Agent '{agent_name}' is not a recognised agent name.",
                code="agent_not_found",
                status_code=404,
            )

        pause_state = self.repository.get_agent_pause_state(agent_name)
        if pause_state and pause_state.is_paused:
            raise AppError(
                message=f"Agent '{agent_name}' is already paused.",
                code="agent_already_paused",
                status_code=409,
            )

        if pause_state is None:
            pause_state = self.repository.create_agent_pause_state(agent_name)

        pause_state.is_paused = True
        pause_state.paused_at = datetime.now(timezone.utc)
        pause_state.pause_reason = pause_reason
        pause_state.resume_condition = resume_condition
        updated_state = self.repository.update_agent_pause_state(pause_state)

        self.repository.create_system_event(
            event_type="agent_paused",
            agent_name=agent_name,
            severity=EventSeverity.INFO,
            message=f"Agent '{agent_name}' paused by operator",
            context_json=None,
            agent_run_id=None,
        )

        response = AgentPauseStateResponse.model_validate(updated_state)
        if self.broadcaster:
            self.broadcaster.broadcast("agent.paused", self._model_dump_pause_state(response))

        return response

    def _validate_recovery_source(self, agent_name: str, pause_state: object) -> dict[str, object] | None:
        """Validate that recovery source exists for the agent. Returns cached checkpoint data."""
        if agent_name in ("firehose", "backfill"):
            from sqlmodel import select
            from datetime import timedelta
            if agent_name == "firehose":
                from app.models import FirehoseProgress
                stmt = select(FirehoseProgress)
                checkpoint = self.repository.session.exec(stmt).first()
                if checkpoint is None:
                    raise AppError(
                        message=f"Cannot resume '{agent_name}': no checkpoint state found.",
                        code="missing_recovery_source",
                        status_code=422,
                    )
                if not checkpoint.resume_required:
                    raise AppError(
                        message=f"Cannot resume '{agent_name}': checkpoint does not require resume.",
                        code="invalid_recovery_source",
                        status_code=422,
                    )
                if checkpoint.next_page is None or checkpoint.active_mode is None:
                    raise AppError(
                        message=f"Cannot resume '{agent_name}': checkpoint is incomplete.",
                        code="invalid_recovery_source",
                        status_code=422,
                    )
                if checkpoint.last_checkpointed_at:
                    age = datetime.now(timezone.utc) - checkpoint.last_checkpointed_at
                    if age > timedelta(hours=24):
                        raise AppError(
                            message=f"Cannot resume '{agent_name}': checkpoint is stale (>24h old).",
                            code="stale_recovery_source",
                            status_code=422,
                        )
                return {
                    "active_mode": checkpoint.active_mode,
                    "next_page": checkpoint.next_page,
                    "resume_required": checkpoint.resume_required,
                }
            else:  # backfill
                from app.models import BackfillProgress
                stmt = select(BackfillProgress)
                checkpoint = self.repository.session.exec(stmt).first()
                if checkpoint is None:
                    raise AppError(
                        message=f"Cannot resume '{agent_name}': no checkpoint state found.",
                        code="missing_recovery_source",
                        status_code=422,
                    )
                if not checkpoint.resume_required:
                    raise AppError(
                        message=f"Cannot resume '{agent_name}': checkpoint does not require resume.",
                        code="invalid_recovery_source",
                        status_code=422,
                    )
                if checkpoint.next_page is None:
                    raise AppError(
                        message=f"Cannot resume '{agent_name}': checkpoint is incomplete.",
                        code="invalid_recovery_source",
                        status_code=422,
                    )
                if checkpoint.last_checkpointed_at:
                    age = datetime.now(timezone.utc) - checkpoint.last_checkpointed_at
                    if age > timedelta(hours=24):
                        raise AppError(
                            message=f"Cannot resume '{agent_name}': checkpoint is stale (>24h old).",
                            code="stale_recovery_source",
                            status_code=422,
                        )
                return {
                    "window_start_date": checkpoint.window_start_date.isoformat() if checkpoint.window_start_date else None,
                    "created_before_boundary": checkpoint.created_before_boundary.isoformat() if checkpoint.created_before_boundary else None,
                    "next_page": checkpoint.next_page,
                    "resume_required": checkpoint.resume_required,
                }
        elif agent_name in ("bouncer", "analyst"):
            from sqlmodel import select, func
            from app.models import RepositoryIntake, RepositoryQueueStatus, RepositoryTriageStatus, RepositoryAnalysisStatus

            if agent_name == "bouncer":
                stmt = select(func.count()).select_from(RepositoryIntake).where(
                    RepositoryIntake.queue_status == RepositoryQueueStatus.PENDING,
                    RepositoryIntake.triage_status == RepositoryTriageStatus.PENDING
                )
            else:  # analyst
                stmt = select(func.count()).select_from(RepositoryIntake).where(
                    RepositoryIntake.triage_status == RepositoryTriageStatus.ACCEPTED,
                    RepositoryIntake.analysis_status != RepositoryAnalysisStatus.COMPLETED
                )

            count = self.repository.session.exec(stmt).one()
            if count == 0:
                raise AppError(
                    message=f"Cannot resume '{agent_name}': no pending work in queue.",
                    code="missing_recovery_source",
                    status_code=422,
                )
            return {"pending_items": count}
        return None

    def _build_recovery_context(self, agent_name: str, cached_checkpoint: dict[str, object] | None = None) -> dict[str, object]:
        """Build recovery context for agent_resumed event."""
        context: dict[str, object] = {"agent_name": agent_name}

        if cached_checkpoint:
            context["checkpoint"] = cached_checkpoint

        return context

    @staticmethod
    def _model_dump_pause_state(model: AgentPauseStateResponse) -> dict[str, object]:
        return dict(model.model_dump(mode="json"))

    def list_incidents(self, params: IncidentListParams) -> list[IncidentResponse]:

        filters = IncidentListFilters(
            agent_name=params.agent_name,
            severity=params.severity,
            classification=params.classification,
            event_type=params.event_type,
            since=params.since,
            limit=params.limit,
        )
        events = self.repository.list_incidents(filters)
        return [self._build_incident_response(event) for event in events]

    def get_incident(self, incident_id: int) -> IncidentResponse | None:

        event = self.repository.get_incident(incident_id)
        if event is None:
            return None
        return self._build_incident_response(event)

    def _build_incident_response(self, event: object) -> IncidentResponse:
        from app.schemas.incident import CheckpointContext, IncidentResponse
        from app.models import SystemEvent

        event_obj = event if isinstance(event, SystemEvent) else event

        # Get related run
        run = None
        if event_obj.agent_run_id:
            run = self.repository.get_agent_run(event_obj.agent_run_id)

        # Parse context
        context = None
        checkpoint_ctx = None
        repo_name = None
        pause_reason = None
        resume_condition = None
        is_paused = False

        if event_obj.context_json:
            try:
                context = json.loads(event_obj.context_json)
                # Extract checkpoint context from event or run error_context
                # Support both firehose (mode/page/anchor_date) and backfill (window_start_date/created_before_boundary)
                if any(k in context for k in ["mode", "page", "anchor_date", "window_start_date", "created_before_boundary"]):
                    checkpoint_ctx = CheckpointContext(
                        mode=context.get("mode"),
                        page=context.get("page"),
                        anchor_date=context.get("anchor_date"),
                        window_start=context.get("window_start") or context.get("window_start_date"),
                        window_end=context.get("window_end") or context.get("created_before_boundary"),
                        resume_required=context.get("resume_required"),
                    )
                repo_name = context.get("full_name")
                # Extract historical pause state from event context
                pause_reason = context.get("pause_reason")
                resume_condition = context.get("resume_condition")
                is_paused = context.get("is_paused", False)
            except (json.JSONDecodeError, TypeError):
                pass

        # Resolve repository name from affected_repository_id if not in context
        if repo_name is None and event_obj.affected_repository_id:
            from app.models import RepositoryIntake
            repo = self.repository.session.get(RepositoryIntake, event_obj.affected_repository_id)
            if repo:
                repo_name = repo.full_name

        # If no checkpoint in event context, try run error_context
        if checkpoint_ctx is None and run and run.error_context:
            try:
                error_ctx = json.loads(run.error_context)
                if any(k in error_ctx for k in ["mode", "page", "anchor_date", "window_start_date", "created_before_boundary"]):
                    checkpoint_ctx = CheckpointContext(
                        mode=error_ctx.get("mode"),
                        page=error_ctx.get("page"),
                        anchor_date=error_ctx.get("anchor_date"),
                        window_start=error_ctx.get("window_start") or error_ctx.get("window_start_date"),
                        window_end=error_ctx.get("window_end") or error_ctx.get("created_before_boundary"),
                        resume_required=error_ctx.get("resume_required"),
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        # Build routing context from Gateway contract
        routing_ctx = None
        try:
            from app.services.openclaw.contract_service import GatewayContractService
            contract_service = GatewayContractService()
            session_surface = contract_service.get_session_surface()
            for session in session_surface.sessions:
                if session.agent_context and session.agent_context.agent_key == event_obj.agent_name:
                    from app.schemas.incident import RoutingContext
                    routing_ctx = RoutingContext(
                        session_id=session.session_id,
                        route_key=session.route_key,
                        agent_key=session.agent_context.agent_key,
                    )
                    break
        except Exception as e:
            logger.warning(f"Failed to fetch routing context for agent {event_obj.agent_name}: {e}")

        # Derive next action
        next_action = self._derive_next_action(event_obj, is_paused)

        return IncidentResponse(
            id=event_obj.id,
            event_type=event_obj.event_type,
            agent_name=event_obj.agent_name,
            severity=event_obj.severity,
            message=event_obj.message,
            created_at=event_obj.created_at,
            failure_classification=event_obj.failure_classification,
            failure_severity=event_obj.failure_severity,
            http_status_code=event_obj.http_status_code,
            retry_after_seconds=event_obj.retry_after_seconds,
            upstream_provider=event_obj.upstream_provider,
            agent_run_id=event_obj.agent_run_id,
            run_status=run.status if run else None,
            run_started_at=run.started_at if run else None,
            run_completed_at=run.completed_at if run else None,
            run_duration_seconds=run.duration_seconds if run else None,
            run_error_summary=run.error_summary if run else None,
            run_error_context=run.error_context if run else None,
            affected_repository_id=event_obj.affected_repository_id,
            repository_full_name=repo_name,
            is_paused=is_paused,
            pause_reason=pause_reason,
            resume_condition=resume_condition,
            checkpoint_context=checkpoint_ctx,
            routing_context=routing_ctx,
            context=context,
            next_action=next_action,
        )

    @staticmethod
    def _derive_next_action(event: object, is_paused: bool) -> str:
        from app.models import FailureClassification

        if is_paused:
            if event.failure_classification == FailureClassification.RATE_LIMITED:
                return "Wait for rate limit to expire, then resume agent in Story 4.6"
            return "Review incident details and resume agent when ready (Story 4.6)"

        if event.failure_classification == FailureClassification.BLOCKING:
            return "Inspect run details and affected repository; manual intervention may be required"

        if event.failure_severity and str(event.failure_severity) == "warning":
            return "Monitor for recurrence; automatic retry will handle transient issues"

        return "Review incident context and determine appropriate action"

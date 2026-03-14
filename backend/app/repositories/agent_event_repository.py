from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import AgentPauseState, AgentRun, AgentRunStatus, EventSeverity, FailureClassification, FailureSeverity, SystemEvent


@dataclass(frozen=True, slots=True)
class AgentRunListFilters:
    agent_name: str | None = None
    status: AgentRunStatus | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class SystemEventListFilters:
    agent_name: str | None = None
    event_type: str | None = None
    severity: EventSeverity | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class FailureEventListFilters:
    agent_name: str | None = None
    classification: FailureClassification | None = None
    severity: FailureSeverity | None = None
    since: datetime | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class IncidentListFilters:
    agent_name: str | None = None
    severity: EventSeverity | None = None
    classification: FailureClassification | None = None
    event_type: str | None = None
    since: datetime | None = None
    limit: int = 50


class AgentEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_agent_run(self, agent_name: str) -> AgentRun:
        record = AgentRun(agent_name=agent_name, status=AgentRunStatus.RUNNING)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def complete_agent_run(
        self,
        run_id: int,
        status: AgentRunStatus,
        items_processed: int | None,
        items_succeeded: int | None,
        items_failed: int | None,
        error_summary: str | None,
        error_context: str | None,
        provider_name: str | None = None,
        model_name: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> AgentRun:
        record = self.session.get(AgentRun, run_id)
        if record is None:
            raise ValueError(f"Agent run {run_id} was not found.")

        completed_at = datetime.now(timezone.utc)
        record.status = status
        record.completed_at = completed_at
        record.duration_seconds = max((completed_at - record.started_at).total_seconds(), 0.0)
        record.items_processed = items_processed
        record.items_succeeded = items_succeeded
        record.items_failed = items_failed
        record.error_summary = error_summary
        record.error_context = error_context
        record.provider_name = provider_name
        record.model_name = model_name
        record.input_tokens = input_tokens
        record.output_tokens = output_tokens
        record.total_tokens = total_tokens
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_agent_runs(self, filters: AgentRunListFilters) -> list[AgentRun]:
        statement = select(AgentRun)
        if filters.agent_name is not None:
            statement = statement.where(AgentRun.agent_name == filters.agent_name)
        if filters.status is not None:
            statement = statement.where(AgentRun.status == filters.status)
        if filters.since is not None:
            statement = statement.where(AgentRun.started_at >= filters.since)
        if filters.until is not None:
            statement = statement.where(AgentRun.started_at <= filters.until)
        statement = statement.order_by(AgentRun.started_at.desc(), AgentRun.id.desc()).limit(
            filters.limit
        )
        return list(self.session.exec(statement).all())

    def get_agent_run(self, run_id: int) -> AgentRun | None:
        return self.session.get(AgentRun, run_id)

    def get_latest_run_per_agent(self) -> list[AgentRun]:
        ranked_runs = (
            select(
                AgentRun.id.label("agent_run_id"),
                func.row_number()
                .over(
                    partition_by=AgentRun.agent_name,
                    order_by=(AgentRun.started_at.desc(), AgentRun.id.desc()),
                )
                .label("rank_order"),
            )
            .subquery()
        )
        statement = (
            select(AgentRun)
            .join(ranked_runs, AgentRun.id == ranked_runs.c.agent_run_id)
            .where(ranked_runs.c.rank_order == 1)
            .order_by(AgentRun.agent_name.asc())
        )
        return list(self.session.exec(statement).all())

    def create_system_event(
        self,
        event_type: str,
        agent_name: str,
        severity: EventSeverity,
        message: str,
        context_json: str | None,
        agent_run_id: int | None,
    ) -> SystemEvent:
        record = SystemEvent(
            event_type=event_type,
            agent_name=agent_name,
            severity=severity,
            message=message,
            context_json=context_json,
            agent_run_id=agent_run_id,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_system_events(self, filters: SystemEventListFilters) -> list[SystemEvent]:
        statement = select(SystemEvent)
        if filters.agent_name is not None:
            statement = statement.where(SystemEvent.agent_name == filters.agent_name)
        if filters.event_type is not None:
            statement = statement.where(SystemEvent.event_type == filters.event_type)
        if filters.severity is not None:
            statement = statement.where(SystemEvent.severity == filters.severity)
        if filters.since is not None:
            statement = statement.where(SystemEvent.created_at >= filters.since)
        if filters.until is not None:
            statement = statement.where(SystemEvent.created_at <= filters.until)
        statement = statement.order_by(SystemEvent.created_at.desc(), SystemEvent.id.desc()).limit(
            filters.limit
        )
        return list(self.session.exec(statement).all())

    def list_system_events_since(self, after_id: int | None, limit: int = 100) -> list[SystemEvent]:
        statement = select(SystemEvent)
        if after_id is not None:
            statement = statement.where(SystemEvent.id > after_id)
        statement = statement.order_by(SystemEvent.id.asc()).limit(limit)
        return list(self.session.exec(statement).all())

    def list_events_for_run(self, run_id: int) -> list[SystemEvent]:
        statement = (
            select(SystemEvent)
            .where(SystemEvent.agent_run_id == run_id)
            .order_by(SystemEvent.created_at.asc(), SystemEvent.id.asc())
        )
        return list(self.session.exec(statement).all())

    def get_latest_system_event_id(self) -> int | None:
        statement = select(SystemEvent.id).order_by(SystemEvent.id.desc()).limit(1)
        return self.session.exec(statement).first()

    def list_failure_events(self, filters: FailureEventListFilters) -> list[SystemEvent]:
        statement = select(SystemEvent).where(
            SystemEvent.failure_classification.isnot(None)  # type: ignore[union-attr]
        )
        if filters.agent_name is not None:
            statement = statement.where(SystemEvent.agent_name == filters.agent_name)
        if filters.classification is not None:
            statement = statement.where(
                SystemEvent.failure_classification == filters.classification
            )
        if filters.severity is not None:
            statement = statement.where(SystemEvent.failure_severity == filters.severity)
        if filters.since is not None:
            statement = statement.where(SystemEvent.created_at >= filters.since)
        statement = statement.order_by(SystemEvent.created_at.desc(), SystemEvent.id.desc()).limit(
            filters.limit
        )
        return list(self.session.exec(statement).all())

    def list_agent_pause_states(self) -> list[AgentPauseState]:
        statement = select(AgentPauseState).order_by(AgentPauseState.agent_name.asc())
        return list(self.session.exec(statement).all())

    def get_agent_pause_state(self, agent_name: str) -> AgentPauseState | None:
        statement = select(AgentPauseState).where(AgentPauseState.agent_name == agent_name)
        return self.session.exec(statement).first()

    def create_agent_pause_state(self, agent_name: str) -> AgentPauseState:
        pause_state = AgentPauseState(agent_name=agent_name, is_paused=False)
        self.session.add(pause_state)
        self.session.commit()
        self.session.refresh(pause_state)
        return pause_state

    def update_agent_pause_state(self, pause_state: AgentPauseState) -> AgentPauseState:
        """Update pause state with optimistic locking to prevent race conditions."""
        from sqlalchemy import update

        current_version = pause_state.version
        new_version = current_version + 1

        # Build values dict dynamically based on operation
        values = {"is_paused": pause_state.is_paused, "version": new_version}
        if pause_state.is_paused:
            values["paused_at"] = pause_state.paused_at
            values["pause_reason"] = pause_state.pause_reason
            values["resume_condition"] = pause_state.resume_condition
            # Clear resume fields when pausing
            values["resumed_at"] = None
            values["resumed_by"] = None
        else:
            values["resumed_at"] = pause_state.resumed_at
            values["resumed_by"] = pause_state.resumed_by
            # Clear pause fields when resuming
            values["pause_reason"] = None
            values["resume_condition"] = None

        stmt = (
            update(AgentPauseState)
            .where(
                AgentPauseState.agent_name == pause_state.agent_name,
                AgentPauseState.version == current_version,
            )
            .values(**values)
        )
        result = self.session.exec(stmt)  # type: ignore[arg-type]
        self.session.commit()

        if result.rowcount == 0:  # type: ignore[attr-defined]
            from app.core.errors import AppError
            raise AppError(
                message=f"Agent '{pause_state.agent_name}' pause state was modified by another operation.",
                code="concurrent_modification",
                status_code=409,
            )

        pause_state.version = new_version
        self.session.refresh(pause_state)
        return pause_state

    def list_incidents(self, filters: IncidentListFilters) -> list[SystemEvent]:
        statement = select(SystemEvent).where(
            (SystemEvent.severity.in_([EventSeverity.ERROR, EventSeverity.CRITICAL]))
            | (SystemEvent.failure_classification.isnot(None))  # type: ignore[union-attr]
        )
        if filters.agent_name is not None:
            statement = statement.where(SystemEvent.agent_name == filters.agent_name)
        if filters.severity is not None:
            statement = statement.where(SystemEvent.severity == filters.severity)
        if filters.classification is not None:
            statement = statement.where(SystemEvent.failure_classification == filters.classification)
        if filters.event_type is not None:
            statement = statement.where(SystemEvent.event_type == filters.event_type)
        if filters.since is not None:
            statement = statement.where(SystemEvent.created_at >= filters.since)
        statement = statement.order_by(SystemEvent.created_at.desc(), SystemEvent.id.desc()).limit(filters.limit)
        return list(self.session.exec(statement).all())

    def get_incident(self, incident_id: int) -> SystemEvent | None:
        statement = select(SystemEvent).where(SystemEvent.id == incident_id)
        return self.session.exec(statement).first()

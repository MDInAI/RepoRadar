from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import EventSeverity, FailureClassification, FailureSeverity, AgentRunStatus


class IncidentListParams(BaseModel):
    agent_name: str | None = None
    severity: EventSeverity | None = None
    classification: FailureClassification | None = None
    event_type: str | None = None
    since: datetime | None = None
    limit: int = Field(default=50, ge=1, le=200)


class CheckpointContext(BaseModel):
    mode: str | None = None
    page: int | None = None
    anchor_date: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    resume_required: bool | None = None


class RoutingContext(BaseModel):
    session_id: str | None = None
    route_key: str | None = None
    agent_key: str | None = None


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    agent_name: str
    severity: EventSeverity
    message: str
    created_at: datetime

    # Failure context
    failure_classification: FailureClassification | None = None
    failure_severity: FailureSeverity | None = None
    http_status_code: int | None = None
    retry_after_seconds: int | None = None
    upstream_provider: str | None = None

    # Related run context
    agent_run_id: int | None = None
    run_status: AgentRunStatus | None = None
    run_started_at: datetime | None = None
    run_completed_at: datetime | None = None
    run_duration_seconds: float | None = None
    run_error_summary: str | None = None
    run_error_context: str | None = None

    # Repository context
    affected_repository_id: int | None = None
    repository_full_name: str | None = None

    # Pause context
    is_paused: bool = False
    pause_reason: str | None = None
    resume_condition: str | None = None

    # Checkpoint context
    checkpoint_context: CheckpointContext | None = None

    # Routing context
    routing_context: RoutingContext | None = None

    # Structured context
    context: dict[str, Any] | None = None

    # Next action guidance
    next_action: str | None = None

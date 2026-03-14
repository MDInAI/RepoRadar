from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import AgentRunStatus, EventSeverity, FailureClassification, FailureSeverity, ResumedBy


class SystemEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    agent_name: str
    severity: EventSeverity
    message: str
    context_json: str | None = None
    agent_run_id: int | None = None
    created_at: datetime
    failure_classification: FailureClassification | None = None
    failure_severity: FailureSeverity | None = None
    http_status_code: int | None = None
    retry_after_seconds: int | None = None
    affected_repository_id: int | None = None
    upstream_provider: str | None = None


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_name: str
    status: AgentRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    items_processed: int | None = None
    items_succeeded: int | None = None
    items_failed: int | None = None
    error_summary: str | None = None


class AgentRunDetailResponse(AgentRunResponse):
    error_context: str | None = None
    events: list[SystemEventResponse] = Field(default_factory=list)


class AgentRunListParams(BaseModel):
    agent_name: str | None = None
    status: AgentRunStatus | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = Field(default=50, ge=1, le=200)


class SystemEventListParams(BaseModel):
    agent_name: str | None = None
    event_type: str | None = None
    severity: EventSeverity | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = Field(default=100, ge=1, le=200)


class AgentStatusEntry(BaseModel):
    agent_name: str
    has_run: bool
    latest_run: AgentRunResponse | None = None


class AgentLatestRunsResponse(BaseModel):
    agents: list[AgentStatusEntry] = Field(default_factory=list)


class FailureEventListParams(BaseModel):
    agent_name: str | None = None
    classification: FailureClassification | None = None
    severity: FailureSeverity | None = None
    since: datetime | None = None
    limit: int = Field(default=50, ge=1, le=200)


class PauseAgentRequest(BaseModel):
    pause_reason: str
    resume_condition: str


class AgentPauseStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_name: str
    is_paused: bool
    paused_at: datetime | None = None
    pause_reason: str | None = None
    resume_condition: str | None = None
    triggered_by_event_id: int | None = None
    resumed_at: datetime | None = None
    resumed_by: ResumedBy | None = None

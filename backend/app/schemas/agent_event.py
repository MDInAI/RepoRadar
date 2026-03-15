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
    provider_name: str | None = None
    model_name: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


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
    display_name: str
    role_label: str
    description: str
    implementation_status: str
    runtime_kind: str
    uses_github_token: bool
    uses_model: bool
    configured_provider: str | None = None
    configured_model: str | None = None
    notes: list[str] = Field(default_factory=list)
    token_usage_24h: int = 0
    input_tokens_24h: int = 0
    output_tokens_24h: int = 0
    has_run: bool
    latest_run: AgentRunResponse | None = None
    latest_intake_summary: dict[str, int] | None = None


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


class AgentManualRunTriggerResponse(BaseModel):
    agent_name: str
    accepted: bool = True
    trigger_mode: str = "background-subprocess"
    triggered_at: datetime
    message: str

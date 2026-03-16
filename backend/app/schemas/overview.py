from __future__ import annotations

from pydantic import BaseModel, Field

from app.models import AgentRunStatus
from app.schemas.agent_event import AgentRuntimeProgress


class IngestionMetrics(BaseModel):
    total_repositories: int
    pending_intake: int
    firehose_discovered: int
    backfill_discovered: int
    discovered_last_24h: int = 0
    firehose_discovered_last_24h: int = 0
    backfill_discovered_last_24h: int = 0


class TriageMetrics(BaseModel):
    pending: int
    accepted: int
    rejected: int


class AnalysisMetrics(BaseModel):
    pending: int
    in_progress: int
    completed: int
    failed: int


class BacklogMetrics(BaseModel):
    queue_pending: int
    queue_in_progress: int
    queue_completed: int
    queue_failed: int
    triage_pending: int
    triage_accepted: int
    triage_rejected: int
    analysis_pending: int
    analysis_in_progress: int
    analysis_completed: int
    analysis_failed: int


class AgentHealthMetrics(BaseModel):
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
    status: AgentRunStatus | None
    is_paused: bool
    last_run_at: str | None
    token_usage_24h: int = 0
    input_tokens_24h: int = 0
    output_tokens_24h: int = 0
    runtime_progress: AgentRuntimeProgress | None = None


class FailureMetrics(BaseModel):
    total_failures: int
    critical_failures: int
    rate_limited_failures: int
    blocking_failures: int


class TokenUsageMetrics(BaseModel):
    total_tokens_24h: int
    input_tokens_24h: int
    output_tokens_24h: int
    llm_runs_24h: int
    top_consumer_agent_name: str | None = None
    top_consumer_tokens_24h: int = 0


class OverviewSummaryResponse(BaseModel):
    ingestion: IngestionMetrics
    triage: TriageMetrics
    analysis: AnalysisMetrics
    backlog: BacklogMetrics
    agents: list[AgentHealthMetrics]
    failures: FailureMetrics
    token_usage: TokenUsageMetrics

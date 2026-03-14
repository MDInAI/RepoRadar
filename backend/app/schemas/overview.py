from __future__ import annotations

from pydantic import BaseModel

from app.models import AgentRunStatus


class IngestionMetrics(BaseModel):
    total_repositories: int
    pending_intake: int
    firehose_discovered: int
    backfill_discovered: int


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
    status: AgentRunStatus | None
    is_paused: bool
    last_run_at: str | None


class FailureMetrics(BaseModel):
    total_failures: int
    critical_failures: int
    rate_limited_failures: int
    blocking_failures: int


class OverviewSummaryResponse(BaseModel):
    ingestion: IngestionMetrics
    triage: TriageMetrics
    analysis: AnalysisMetrics
    backlog: BacklogMetrics
    agents: list[AgentHealthMetrics]
    failures: FailureMetrics

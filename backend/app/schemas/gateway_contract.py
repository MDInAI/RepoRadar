from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


GatewayRuntimeMode = Literal["multi-agent"]
GatewayAgentKey = Literal[
    "overlord",
    "firehose",
    "backfill",
    "bouncer",
    "analyst",
    "combiner",
    "obsession",
]
GatewayAgentRole = Literal[
    "control-plane-coordinator",
    "repository-intake-firehose",
    "repository-intake-backfill",
    "repository-triage",
    "repository-analysis",
    "idea-synthesis",
    "idea-tracking",
]
GatewayAgentDisplayName = Literal[
    "Overlord",
    "Firehose",
    "Backfill",
    "Bouncer",
    "Analyst",
    "Combiner",
    "Obsession",
]
GatewayAgentLifecycleState = Literal["planned", "reserved"]
GatewayAgentMVPScope = Literal["initial", "reserved"]


class GatewayAuthorityBoundary(BaseModel):
    owner: Literal["gateway", "agentic-workflow", "workspace"]
    state_domains: list[str] = Field(default_factory=list)
    boundary: str


class GatewayCanonicalInterface(BaseModel):
    name: Literal[
        "runtime-inspection",
        "session-discovery",
        "session-detail-history",
        "realtime-events",
    ]
    canonical_source: str
    app_surface: str
    contract_status: Literal["defined", "reserved"]
    notes: str


class GatewayDependencyLink(BaseModel):
    story: str
    expectation: str


class GatewayTransportTarget(BaseModel):
    configured: bool
    url: str | None = None
    scheme: Literal["ws", "wss"] | None = None
    allow_insecure_tls: bool = False
    token_configured: bool = False
    source: str
    notes: list[str] = Field(default_factory=list)


class GatewayEventEnvelopeField(BaseModel):
    name: str
    type: str
    description: str


class GatewayEventEnvelope(BaseModel):
    version: str
    channel: str
    delivery: str
    fields: list[GatewayEventEnvelopeField] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class GatewayFrontendBoundary(BaseModel):
    flow: str
    direct_browser_gateway_access: bool
    notes: list[str] = Field(default_factory=list)


class GatewayAgentQueuePlaceholder(BaseModel):
    status: Literal["reserved"] = "reserved"
    pending_items: int | None = None
    notes: list[str] = Field(default_factory=list)


class GatewayQueueStateBuckets(BaseModel):
    pending: int = 0
    in_progress: int = 0
    completed: int = 0
    failed: int = 0


class GatewayAgentIntakeCheckpoint(BaseModel):
    kind: Literal["firehose", "backfill"]
    next_page: int = 1
    last_checkpointed_at: datetime | None = None
    mirror_snapshot_generated_at: datetime | None = None
    active_mode: Literal["new", "trending"] | None = None
    resume_required: bool | None = None
    new_anchor_date: date | None = None
    trending_anchor_date: date | None = None
    run_started_at: datetime | None = None
    window_start_date: date | None = None
    created_before_boundary: date | None = None
    created_before_cursor: datetime | None = None
    exhausted: bool | None = None


class GatewayAgentIntakeQueueSummary(BaseModel):
    status: Literal["live"] = "live"
    source_of_truth: Literal["agentic-workflow"] = "agentic-workflow"
    pending_items: int = 0
    total_items: int = 0
    state_counts: GatewayQueueStateBuckets = Field(default_factory=GatewayQueueStateBuckets)
    checkpoint: GatewayAgentIntakeCheckpoint
    notes: list[str] = Field(default_factory=list)


GatewayAgentQueue = GatewayAgentQueuePlaceholder | GatewayAgentIntakeQueueSummary


class GatewayAgentMonitoringPlaceholder(BaseModel):
    status: Literal["reserved"] = "reserved"
    last_heartbeat_at: str | None = None
    notes: list[str] = Field(default_factory=list)


class GatewayAgentSessionAffinity(BaseModel):
    source_of_truth: Literal["gateway"] = "gateway"
    session_id: str | None = None
    route_key: str | None = None
    status: Literal["reserved"] = "reserved"


class GitHubApiBudgetSnapshot(BaseModel):
    provider: Literal["github"] = "github"
    captured_at: datetime
    last_response_status: int | None = None
    request_url: str | None = None
    resource: str | None = None
    limit: int | None = None
    remaining: int | None = None
    used: int | None = None
    reset_at: datetime | None = None
    retry_after_seconds: int | None = None
    exhausted: bool | None = None


class GatewayNamedAgentSummary(BaseModel):
    agent_key: GatewayAgentKey
    display_name: GatewayAgentDisplayName
    agent_role: GatewayAgentRole
    lifecycle_state: GatewayAgentLifecycleState
    mvp_scope: GatewayAgentMVPScope
    queue: GatewayAgentQueue
    monitoring: GatewayAgentMonitoringPlaceholder
    session_affinity: GatewayAgentSessionAffinity
    notes: list[str] = Field(default_factory=list)


class GatewaySessionAgentContext(BaseModel):
    agent_key: GatewayAgentKey
    display_name: GatewayAgentDisplayName
    agent_role: GatewayAgentRole


class GatewayContractResponse(BaseModel):
    contract_version: str
    architecture_flow: str
    runtime_mode: GatewayRuntimeMode
    named_agents: list[GatewayNamedAgentSummary] = Field(default_factory=list)
    authority_boundary: list[GatewayAuthorityBoundary] = Field(default_factory=list)
    frontend_boundary: GatewayFrontendBoundary
    canonical_interfaces: list[GatewayCanonicalInterface] = Field(default_factory=list)
    transport_target: GatewayTransportTarget
    dependency_chain: list[GatewayDependencyLink] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    event_envelope: GatewayEventEnvelope


class NormalizedGatewayRuntimeState(BaseModel):
    source_of_truth: str
    runtime_mode: GatewayRuntimeMode
    gateway_url: str | None = None
    connection_state: Literal["reserved"]
    status: Literal["unknown"]
    route_owner: str
    agent_states: list[GatewayNamedAgentSummary] = Field(default_factory=list)
    github_api_budget: GitHubApiBudgetSnapshot | None = None
    notes: list[str] = Field(default_factory=list)


class GatewayRuntimeSurfaceResponse(BaseModel):
    contract_version: str
    availability: Literal["available", "reserved"]
    runtime: NormalizedGatewayRuntimeState


class NormalizedGatewaySessionSummary(BaseModel):
    session_id: str
    route_key: str | None = None
    status: Literal["reserved"] = "reserved"
    updated_at: str | None = None
    agent_context: GatewaySessionAgentContext | None = None


class GatewaySessionSurfaceResponse(BaseModel):
    contract_version: str
    availability: Literal["reserved"]
    runtime_mode: GatewayRuntimeMode
    source_of_truth: str
    named_agents: list[GatewayNamedAgentSummary] = Field(default_factory=list)
    sessions: list[NormalizedGatewaySessionSummary] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class NormalizedGatewaySessionDetail(BaseModel):
    session_id: str
    label: str | None = None
    route_key: str | None = None
    status: Literal["reserved"] = "reserved"
    agent_context: GatewaySessionAgentContext | None = None
    transcript_available: bool = False
    notes: list[str] = Field(default_factory=list)


class GatewaySessionDetailResponse(BaseModel):
    contract_version: str
    availability: Literal["reserved"]
    source_of_truth: str
    session: NormalizedGatewaySessionDetail


class NormalizedGatewayHistoryEntry(BaseModel):
    entry_id: str
    role: str
    content: str | None = None
    emitted_at: str | None = None
    status: Literal["reserved"] = "reserved"


class GatewaySessionHistorySurfaceResponse(BaseModel):
    contract_version: str
    availability: Literal["reserved"]
    source_of_truth: str
    session_id: str
    history: list[NormalizedGatewayHistoryEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class GatewayEventEnvelopeResponse(BaseModel):
    contract_version: str
    envelope: GatewayEventEnvelope

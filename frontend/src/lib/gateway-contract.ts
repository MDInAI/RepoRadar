export const gatewayContractEndpoints = {
  contract: "/api/v1/gateway/contract",
  runtime: "/api/v1/gateway/runtime",
  sessions: "/api/v1/gateway/sessions",
  sessionDetail: (sessionId: string) => `/api/v1/gateway/sessions/${sessionId}`,
  sessionHistory: (sessionId: string) =>
    `/api/v1/gateway/sessions/${sessionId}/history`,
  eventEnvelope: "/api/v1/gateway/events/envelope",
} as const;

export type GatewayOwner = "gateway" | "agentic-workflow" | "workspace";
export type GatewayContractStatus = "defined" | "reserved";
export type GatewayRuntimeMode = "multi-agent";
export type GatewayAgentKey =
  | "overlord"
  | "firehose"
  | "backfill"
  | "bouncer"
  | "analyst"
  | "combiner"
  | "obsession";
export type GatewayAgentDisplayName =
  | "Overlord"
  | "Firehose"
  | "Backfill"
  | "Bouncer"
  | "Analyst"
  | "Combiner"
  | "Obsession";
export type GatewayAgentRole =
  | "control-plane-coordinator"
  | "repository-intake-firehose"
  | "repository-intake-backfill"
  | "repository-triage"
  | "repository-analysis"
  | "idea-synthesis"
  | "idea-tracking";
export type GatewayAgentLifecycleState = "planned" | "reserved";
export type GatewayAgentMVPScope = "initial" | "reserved";

export interface GatewayAuthorityBoundary {
  owner: GatewayOwner;
  state_domains: string[];
  boundary: string;
}

export interface GatewayCanonicalInterface {
  name:
    | "runtime-inspection"
    | "session-discovery"
    | "session-detail-history"
    | "realtime-events";
  canonical_source: string;
  app_surface: string;
  contract_status: GatewayContractStatus;
  notes: string;
}

export interface GatewayDependencyLink {
  story: string;
  expectation: string;
}

export interface GatewayTransportTarget {
  configured: boolean;
  url: string | null;
  scheme: "ws" | "wss" | null;
  allow_insecure_tls: boolean;
  token_configured: boolean;
  source: string;
  notes: string[];
}

export interface GatewayFrontendBoundary {
  flow: string;
  direct_browser_gateway_access: boolean;
  notes: string[];
}

export interface GatewayEventEnvelopeField {
  name: string;
  type: string;
  description: string;
}

export interface GatewayEventEnvelope {
  version: string;
  channel: string;
  delivery: string;
  fields: GatewayEventEnvelopeField[];
  notes: string[];
}

export interface GatewayAgentQueuePlaceholder {
  status: "reserved";
  pending_items: number | null;
  notes: string[];
}

export interface GatewayQueueStateBuckets {
  pending: number;
  in_progress: number;
  completed: number;
  failed: number;
}

interface GatewayAgentIntakeCheckpointBase {
  next_page: number;
  last_checkpointed_at: string | null;
  mirror_snapshot_generated_at: string | null;
}

export interface GatewayFirehoseIntakeCheckpoint
  extends GatewayAgentIntakeCheckpointBase {
  kind: "firehose";
  active_mode: "new" | "trending" | null;
  resume_required: boolean | null;
  new_anchor_date: string | null;
  trending_anchor_date: string | null;
  run_started_at: string | null;
}

export interface GatewayBackfillIntakeCheckpoint
  extends GatewayAgentIntakeCheckpointBase {
  kind: "backfill";
  window_start_date: string | null;
  created_before_boundary: string | null;
  created_before_cursor: string | null;
  exhausted: boolean | null;
}

export type GatewayAgentIntakeCheckpoint =
  | GatewayFirehoseIntakeCheckpoint
  | GatewayBackfillIntakeCheckpoint;

export interface GatewayAgentIntakeQueueSummary {
  status: "live";
  source_of_truth: "agentic-workflow";
  pending_items: number;
  total_items: number;
  state_counts: GatewayQueueStateBuckets;
  checkpoint: GatewayAgentIntakeCheckpoint;
  notes: string[];
}

export type GatewayAgentQueue =
  | GatewayAgentQueuePlaceholder
  | GatewayAgentIntakeQueueSummary;

export interface GatewayAgentMonitoringPlaceholder {
  status: "reserved";
  last_heartbeat_at: string | null;
  notes: string[];
}

export interface GatewayAgentSessionAffinity {
  source_of_truth: "gateway";
  session_id: string | null;
  route_key: string | null;
  status: "reserved";
}

export interface GatewayNamedAgentSummary {
  agent_key: GatewayAgentKey;
  display_name: GatewayAgentDisplayName;
  agent_role: GatewayAgentRole;
  lifecycle_state: GatewayAgentLifecycleState;
  mvp_scope: GatewayAgentMVPScope;
  queue: GatewayAgentQueue;
  monitoring: GatewayAgentMonitoringPlaceholder;
  session_affinity: GatewayAgentSessionAffinity;
  notes: string[];
}

export interface GitHubApiBudgetSnapshot {
  provider: "github";
  captured_at: string;
  last_response_status: number | null;
  request_url: string | null;
  resource: string | null;
  limit: number | null;
  remaining: number | null;
  used: number | null;
  reset_at: string | null;
  retry_after_seconds: number | null;
  exhausted: boolean | null;
}

export interface GatewaySessionAgentContext {
  agent_key: GatewayAgentKey;
  display_name: GatewayAgentDisplayName;
  agent_role: GatewayAgentRole;
}

export interface GatewayContractResponse {
  contract_version: string;
  architecture_flow: string;
  runtime_mode: GatewayRuntimeMode;
  named_agents: GatewayNamedAgentSummary[];
  authority_boundary: GatewayAuthorityBoundary[];
  frontend_boundary: GatewayFrontendBoundary;
  canonical_interfaces: GatewayCanonicalInterface[];
  transport_target: GatewayTransportTarget;
  dependency_chain: GatewayDependencyLink[];
  constraints: string[];
  event_envelope: GatewayEventEnvelope;
}

export interface GatewayRuntimeSurfaceResponse {
  contract_version: string;
  availability: "available" | "reserved";
  runtime: {
    source_of_truth: string;
    runtime_mode: GatewayRuntimeMode;
    gateway_url: string | null;
    connection_state: "reserved";
    status: "unknown";
    route_owner: string;
    agent_states: GatewayNamedAgentSummary[];
    github_api_budget: GitHubApiBudgetSnapshot | null;
    notes: string[];
  };
}

export interface GatewaySessionSummary {
  session_id: string;
  route_key: string | null;
  status: "reserved";
  updated_at: string | null;
  agent_context: GatewaySessionAgentContext | null;
}

export interface GatewaySessionSurfaceResponse {
  contract_version: string;
  availability: "reserved";
  runtime_mode: GatewayRuntimeMode;
  source_of_truth: "gateway";
  named_agents: GatewayNamedAgentSummary[];
  sessions: GatewaySessionSummary[];
  notes: string[];
}

export interface GatewaySessionDetailResponse {
  contract_version: string;
  availability: "reserved";
  source_of_truth: "gateway";
  session: {
    session_id: string;
    label: string | null;
    route_key: string | null;
    status: "reserved";
    agent_context: GatewaySessionAgentContext | null;
    transcript_available: boolean;
    notes: string[];
  };
}

export interface GatewaySessionHistoryEntry {
  entry_id: string;
  role: string;
  content: string | null;
  emitted_at: string | null;
  status: "reserved";
}

export interface GatewaySessionHistoryResponse {
  contract_version: string;
  availability: "reserved";
  source_of_truth: "gateway";
  session_id: string;
  history: GatewaySessionHistoryEntry[];
  notes: string[];
}

export interface GatewayEventEnvelopeResponse {
  contract_version: string;
  envelope: GatewayEventEnvelope;
}

// Frontend pages should consume Gateway data through the backend contract only.

export function isGatewayContractResponse(value: unknown): value is GatewayContractResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as GatewayContractResponse).contract_version === "string" &&
    typeof (value as GatewayContractResponse).runtime_mode === "string" &&
    Array.isArray((value as GatewayContractResponse).named_agents)
  );
}

export function isGatewayRuntimeSurfaceResponse(
  value: unknown,
): value is GatewayRuntimeSurfaceResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as GatewayRuntimeSurfaceResponse).contract_version === "string" &&
    typeof (value as GatewayRuntimeSurfaceResponse).availability === "string" &&
    typeof (value as GatewayRuntimeSurfaceResponse).runtime === "object" &&
    (value as GatewayRuntimeSurfaceResponse).runtime !== null
  );
}

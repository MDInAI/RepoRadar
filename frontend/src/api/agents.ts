import { getRequiredApiBaseUrl } from "./base-url";

export type AgentName =
  | "overlord"
  | "firehose"
  | "backfill"
  | "bouncer"
  | "analyst"
  | "combiner"
  | "obsession"
  | "idea_scout";

export type AgentRunStatus =
  | "running"
  | "completed"
  | "failed"
  | "skipped"
  | "skipped_paused";
export type EventSeverity = "info" | "warning" | "error" | "critical";
export type FailureClassification = "retryable" | "blocking" | "rate_limited";
export type FailureSeverityLevel = "warning" | "error" | "critical";

export interface AgentRunEvent {
  id: number;
  agent_name: AgentName;
  status: AgentRunStatus;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  items_processed: number | null;
  items_succeeded: number | null;
  items_failed: number | null;
  error_summary: string | null;
  provider_name: string | null;
  model_name: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
}

export interface AgentRunDetailResponse extends AgentRunEvent {
  error_context: string | null;
  events: SystemEventPayload[];
}

export interface AgentRuntimeProgress {
  status_label: string;
  current_activity: string;
  current_target: string | null;
  progress_percent: number | null;
  primary_counts_label: string | null;
  completed_count: number | null;
  total_count: number | null;
  remaining_count: number | null;
  unit_label: string | null;
  secondary_counts_label: string | null;
  secondary_completed_count: number | null;
  secondary_total_count: number | null;
  secondary_remaining_count: number | null;
  secondary_unit_label: string | null;
  updated_at: string | null;
  source: string;
  details: string[];
}

export interface SystemEventPayload {
  id: number;
  event_type: string;
  agent_name: AgentName;
  severity: EventSeverity;
  message: string;
  context_json: string | null;
  agent_run_id: number | null;
  created_at: string;
}

export interface FailureEventPayload extends SystemEventPayload {
  failure_classification: FailureClassification | null;
  failure_severity: FailureSeverityLevel | null;
  http_status_code: number | null;
  retry_after_seconds: number | null;
  affected_repository_id: number | null;
  upstream_provider: string | null;
}

export interface AgentStatusEntry {
  agent_name: AgentName;
  display_name: string;
  role_label: string;
  description: string;
  implementation_status: string;
  runtime_kind: string;
  uses_github_token: boolean;
  uses_model: boolean;
  configured_provider: string | null;
  configured_model: string | null;
  notes: string[];
  token_usage_24h: number;
  input_tokens_24h: number;
  output_tokens_24h: number;
  has_run: boolean;
  latest_run: AgentRunEvent | null;
  latest_intake_summary: {
    fetched: number;
    inserted: number;
    skipped: number;
    duplicates: number;
    failed_outcomes: number;
  } | null;
  runtime_progress?: AgentRuntimeProgress | null;
}

export interface AgentLatestRunsResponse {
  agents: AgentStatusEntry[];
}

export interface AgentRunListParams {
  agent_name?: AgentName | null;
  status?: AgentRunStatus | null;
  since?: string | null;
  until?: string | null;
  limit?: number;
}

export interface SystemEventListParams {
  agent_name?: AgentName | null;
  event_type?: string | null;
  severity?: EventSeverity | null;
  since?: string | null;
  until?: string | null;
  limit?: number;
}

export interface FailureEventListParams {
  agent_name?: AgentName | null;
  classification?: FailureClassification | null;
  severity?: FailureSeverityLevel | null;
  since?: string | null;
  limit?: number;
}

export interface AgentPauseState {
  agent_name: AgentName;
  is_paused: boolean;
  paused_at: string | null;
  pause_reason: string | null;
  resume_condition: string | null;
  triggered_by_event_id: number | null;
  resumed_at: string | null;
  resumed_by: string | null;
}

export interface AgentManualRunTriggerResponse {
  agent_name: AgentName;
  accepted: boolean;
  trigger_mode: string;
  triggered_at: string;
  message: string;
}

export type AgentConfigInputKind = "integer" | "date" | "csv" | "text" | "select";

export interface AgentConfigField {
  key: string;
  label: string;
  description: string;
  input_kind: AgentConfigInputKind;
  value: string;
  options: string[];
  unit: string | null;
  min_value: number | null;
  placeholder: string | null;
}

export interface AgentConfigResponse {
  agent_name: AgentName;
  display_name: string;
  editable: boolean;
  summary: string;
  apply_notes: string[];
  fields: AgentConfigField[];
}

export interface AgentConfigUpdateResponse extends AgentConfigResponse {
  message: string;
}

export interface BackfillTimelineResponse {
  agent_name: "backfill";
  oldest_date_in_window: string;
  newest_boundary_exclusive: string;
  current_cursor: string | null;
  next_page: number;
  exhausted: boolean;
  resume_required: boolean;
  last_checkpointed_at: string | null;
  summary: string;
  notes: string[];
}

export interface BackfillTimelineUpdateResponse extends BackfillTimelineResponse {
  message: string;
}

export interface ArtifactStorageStatusResponse {
  artifact_metadata_count: number;
  artifact_payload_count: number;
  missing_payload_count: number;
  payload_coverage_ratio: number;
  payload_coverage_percent: number;
  legacy_readme_file_count: number;
  legacy_analysis_file_count: number;
  legacy_file_count: number;
  artifact_debug_mirror_enabled: boolean;
  safe_to_prune_legacy_files: boolean;
  prune_readiness_reason: string;
}

interface AgentErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
  };
}

const FETCH_TIMEOUT_MS = 10_000;
const DEFAULT_RUN_LIMIT = 50;
const DEFAULT_EVENT_LIMIT = 40;
const MAX_LIST_LIMIT = 200;

export const AGENT_DISPLAY_ORDER: AgentName[] = [
  "overlord",
  "firehose",
  "backfill",
  "idea_scout",
  "bouncer",
  "analyst",
  "combiner",
  "obsession",
] as const;

const RUN_STATUSES: AgentRunStatus[] = [
  "running",
  "completed",
  "failed",
  "skipped",
  "skipped_paused",
];
const EVENT_SEVERITIES: EventSeverity[] = ["info", "warning", "error", "critical"];

export class AgentRequestError extends Error {
  status: number;
  code: string | null;
  details: Record<string, unknown>;

  constructor(
    message: string,
    options: {
      status: number;
      code?: string | null;
      details?: Record<string, unknown>;
    },
  ) {
    super(message);
    this.name = "AgentRequestError";
    this.status = options.status;
    this.code = options.code ?? null;
    this.details = options.details ?? {};
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isAgentErrorEnvelope(payload: unknown): payload is AgentErrorEnvelope {
  return isRecord(payload) && (!("error" in payload) || isRecord(payload.error));
}

function isNullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}

function isNullableNumber(value: unknown): value is number | null {
  return typeof value === "number" || value === null;
}

function isAgentName(value: unknown): value is AgentName {
  return typeof value === "string" && AGENT_DISPLAY_ORDER.includes(value as AgentName);
}

function isAgentRunStatus(value: unknown): value is AgentRunStatus {
  return typeof value === "string" && RUN_STATUSES.includes(value as AgentRunStatus);
}

function isEventSeverity(value: unknown): value is EventSeverity {
  return typeof value === "string" && EVENT_SEVERITIES.includes(value as EventSeverity);
}

function isFailureClassification(value: unknown): value is FailureClassification {
  return value === "retryable" || value === "blocking" || value === "rate_limited";
}

function isFailureSeverityLevel(value: unknown): value is FailureSeverityLevel {
  return value === "warning" || value === "error" || value === "critical";
}

function isAgentPauseState(value: unknown): value is AgentPauseState {
  return (
    isRecord(value) &&
    isAgentName(value.agent_name) &&
    typeof value.is_paused === "boolean" &&
    isNullableString(value.paused_at) &&
    isNullableString(value.pause_reason) &&
    isNullableString(value.resume_condition) &&
    (typeof value.triggered_by_event_id === "number" || value.triggered_by_event_id === null) &&
    isNullableString(value.resumed_at) &&
    isNullableString(value.resumed_by)
  );
}

function isAgentManualRunTriggerResponse(value: unknown): value is AgentManualRunTriggerResponse {
  return (
    isRecord(value) &&
    isAgentName(value.agent_name) &&
    typeof value.accepted === "boolean" &&
    typeof value.trigger_mode === "string" &&
    typeof value.triggered_at === "string" &&
    typeof value.message === "string"
  );
}

function isAgentConfigInputKind(value: unknown): value is AgentConfigInputKind {
  return value === "integer" || value === "date" || value === "csv" || value === "text" || value === "select";
}

function isAgentConfigField(value: unknown): value is AgentConfigField {
  return (
    isRecord(value) &&
    typeof value.key === "string" &&
    typeof value.label === "string" &&
    typeof value.description === "string" &&
    isAgentConfigInputKind(value.input_kind) &&
    typeof value.value === "string" &&
    Array.isArray(value.options) &&
    value.options.every((option) => typeof option === "string") &&
    (typeof value.unit === "string" || value.unit === null) &&
    (typeof value.min_value === "number" || value.min_value === null) &&
    (typeof value.placeholder === "string" || value.placeholder === null)
  );
}

function isAgentConfigResponse(value: unknown): value is AgentConfigResponse {
  return (
    isRecord(value) &&
    isAgentName(value.agent_name) &&
    typeof value.display_name === "string" &&
    typeof value.editable === "boolean" &&
    typeof value.summary === "string" &&
    Array.isArray(value.apply_notes) &&
    value.apply_notes.every((note) => typeof note === "string") &&
    Array.isArray(value.fields) &&
    value.fields.every(isAgentConfigField)
  );
}

function isAgentConfigUpdateResponse(value: unknown): value is AgentConfigUpdateResponse {
  return isAgentConfigResponse(value) && isRecord(value) && typeof value.message === "string";
}

function isBackfillTimelineResponse(value: unknown): value is BackfillTimelineResponse {
  return (
    isRecord(value) &&
    value.agent_name === "backfill" &&
    typeof value.oldest_date_in_window === "string" &&
    typeof value.newest_boundary_exclusive === "string" &&
    isNullableString(value.current_cursor) &&
    typeof value.next_page === "number" &&
    typeof value.exhausted === "boolean" &&
    typeof value.resume_required === "boolean" &&
    isNullableString(value.last_checkpointed_at) &&
    typeof value.summary === "string" &&
    Array.isArray(value.notes) &&
    value.notes.every((note) => typeof note === "string")
  );
}

function isBackfillTimelineUpdateResponse(value: unknown): value is BackfillTimelineUpdateResponse {
  return isBackfillTimelineResponse(value) && isRecord(value) && typeof value.message === "string";
}

function isArtifactStorageStatusResponse(value: unknown): value is ArtifactStorageStatusResponse {
  return (
    isRecord(value) &&
    typeof value.artifact_metadata_count === "number" &&
    typeof value.artifact_payload_count === "number" &&
    typeof value.missing_payload_count === "number" &&
    typeof value.payload_coverage_ratio === "number" &&
    typeof value.payload_coverage_percent === "number" &&
    typeof value.legacy_readme_file_count === "number" &&
    typeof value.legacy_analysis_file_count === "number" &&
    typeof value.legacy_file_count === "number" &&
    typeof value.artifact_debug_mirror_enabled === "boolean" &&
    typeof value.safe_to_prune_legacy_files === "boolean" &&
    typeof value.prune_readiness_reason === "string"
  );
}

export function isAgentRunEvent(value: unknown): value is AgentRunEvent {
  return (
    isRecord(value) &&
    typeof value.id === "number" &&
    isAgentName(value.agent_name) &&
    isAgentRunStatus(value.status) &&
    typeof value.started_at === "string" &&
    isNullableString(value.completed_at) &&
    isNullableNumber(value.duration_seconds) &&
    isNullableNumber(value.items_processed) &&
    isNullableNumber(value.items_succeeded) &&
    isNullableNumber(value.items_failed) &&
    isNullableString(value.error_summary) &&
    isNullableString(value.provider_name) &&
    isNullableString(value.model_name) &&
    isNullableNumber(value.input_tokens) &&
    isNullableNumber(value.output_tokens) &&
    isNullableNumber(value.total_tokens)
  );
}

export function isSystemEventPayload(value: unknown): value is SystemEventPayload {
  return (
    isRecord(value) &&
    typeof value.id === "number" &&
    typeof value.event_type === "string" &&
    isAgentName(value.agent_name) &&
    isEventSeverity(value.severity) &&
    typeof value.message === "string" &&
    isNullableString(value.context_json) &&
    isNullableNumber(value.agent_run_id) &&
    typeof value.created_at === "string"
  );
}

function isFailureEventPayload(value: unknown): value is FailureEventPayload {
  return (
    isSystemEventPayload(value) &&
    isRecord(value) &&
    (value.failure_classification === null || isFailureClassification(value.failure_classification)) &&
    (value.failure_severity === null || isFailureSeverityLevel(value.failure_severity)) &&
    isNullableNumber(value.http_status_code) &&
    isNullableNumber(value.retry_after_seconds) &&
    isNullableNumber(value.affected_repository_id) &&
    isNullableString(value.upstream_provider)
  );
}

function isAgentRunDetailResponse(value: unknown): value is AgentRunDetailResponse {
  return (
    isAgentRunEvent(value) &&
    isRecord(value) &&
    isNullableString(value.error_context) &&
    Array.isArray(value.events) &&
    value.events.every(isSystemEventPayload)
  );
}

function isAgentStatusEntry(value: unknown): value is AgentStatusEntry {
  return (
    isRecord(value) &&
    isAgentName(value.agent_name) &&
    typeof value.display_name === "string" &&
    typeof value.role_label === "string" &&
    typeof value.description === "string" &&
    typeof value.implementation_status === "string" &&
    typeof value.runtime_kind === "string" &&
    typeof value.uses_github_token === "boolean" &&
    typeof value.uses_model === "boolean" &&
    isNullableString(value.configured_provider) &&
    isNullableString(value.configured_model) &&
    Array.isArray(value.notes) &&
    value.notes.every(note => typeof note === "string") &&
    typeof value.token_usage_24h === "number" &&
    typeof value.input_tokens_24h === "number" &&
    typeof value.output_tokens_24h === "number" &&
    typeof value.has_run === "boolean" &&
    (value.latest_run === null || isAgentRunEvent(value.latest_run)) &&
    (value.latest_intake_summary === null ||
      (isRecord(value.latest_intake_summary) &&
        typeof value.latest_intake_summary.fetched === "number" &&
        typeof value.latest_intake_summary.inserted === "number" &&
        typeof value.latest_intake_summary.skipped === "number" &&
        typeof value.latest_intake_summary.duplicates === "number" &&
        typeof value.latest_intake_summary.failed_outcomes === "number")) &&
    (!("runtime_progress" in value) ||
      value.runtime_progress === null ||
      (isRecord(value.runtime_progress) &&
        typeof value.runtime_progress.status_label === "string" &&
        typeof value.runtime_progress.current_activity === "string" &&
        isNullableString(value.runtime_progress.current_target) &&
        isNullableNumber(value.runtime_progress.progress_percent) &&
        isNullableString(value.runtime_progress.primary_counts_label) &&
        isNullableNumber(value.runtime_progress.completed_count) &&
        isNullableNumber(value.runtime_progress.total_count) &&
        isNullableNumber(value.runtime_progress.remaining_count) &&
        isNullableString(value.runtime_progress.unit_label) &&
        isNullableString(value.runtime_progress.secondary_counts_label) &&
        isNullableNumber(value.runtime_progress.secondary_completed_count) &&
        isNullableNumber(value.runtime_progress.secondary_total_count) &&
        isNullableNumber(value.runtime_progress.secondary_remaining_count) &&
        isNullableString(value.runtime_progress.secondary_unit_label) &&
        isNullableString(value.runtime_progress.updated_at) &&
        typeof value.runtime_progress.source === "string" &&
        Array.isArray(value.runtime_progress.details) &&
        value.runtime_progress.details.every((detail) => typeof detail === "string")))
  );
}

function isAgentLatestRunsResponse(value: unknown): value is AgentLatestRunsResponse {
  return (
    isRecord(value) &&
    Array.isArray(value.agents) &&
    value.agents.every(isAgentStatusEntry)
  );
}

function parseExpectedResponse<T>(
  value: unknown,
  guard: (payload: unknown) => payload is T,
  message: string,
  code: string,
): T {
  if (!guard(value)) {
    throw new AgentRequestError(message, {
      status: 0,
      code,
    });
  }
  return value;
}

function buildSearchParams(
  params: Record<string, string | number | null | undefined>,
): URLSearchParams {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") {
      continue;
    }
    searchParams.set(key, String(value));
  }
  return searchParams;
}

function validateListLimit(
  limit: number | undefined,
  fallback: number,
  code: string,
): number {
  const resolved = limit ?? fallback;
  if (!Number.isInteger(resolved) || resolved < 1 || resolved > MAX_LIST_LIMIT) {
    throw new AgentRequestError(`Limit must be an integer between 1 and ${MAX_LIST_LIMIT}.`, {
      status: 0,
      code,
      details: {
        limit: resolved,
        max_limit: MAX_LIST_LIMIT,
      },
    });
  }
  return resolved;
}

async function requestJson<T>(
  path: string,
  params?: URLSearchParams,
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  try {
    const search = params && [...params.keys()].length > 0 ? `?${params.toString()}` : "";
    const response = await fetch(`${getRequiredApiBaseUrl()}${path}${search}`, {
      cache: "no-store",
      signal: controller.signal,
    });

    if (response.ok) {
      return response.json() as Promise<T>;
    }

    let payload: AgentErrorEnvelope | null = null;
    try {
      const raw: unknown = await response.json();
      payload = isAgentErrorEnvelope(raw) ? raw : null;
    } catch {
      payload = null;
    }

    throw new AgentRequestError(
      payload?.error?.message ||
        `Failed to fetch agent data: ${response.status} ${response.statusText}`.trim(),
      {
        status: response.status,
        code: payload?.error?.code ?? null,
        details: payload?.error?.details ?? {},
      },
    );
  } catch (error) {
    if (error instanceof AgentRequestError) {
      throw error;
    }
    if (error instanceof Error && error.name === "AbortError") {
      throw new AgentRequestError("Request timed out fetching agent data.", {
        status: 0,
        code: "request_timeout",
      });
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeoutId);
  }
}

async function mutateJson<T>(
  path: string,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  body?: unknown,
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  try {
    const response = await fetch(`${getRequiredApiBaseUrl()}${path}`, {
      method,
      cache: "no-store",
      signal: controller.signal,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (response.ok) {
      return response.json() as Promise<T>;
    }

    let payload: AgentErrorEnvelope | null = null;
    try {
      const raw: unknown = await response.json();
      payload = isAgentErrorEnvelope(raw) ? raw : null;
    } catch {
      payload = null;
    }

    throw new AgentRequestError(
      payload?.error?.message ||
        `Failed to mutate agent data: ${response.status} ${response.statusText}`.trim(),
      {
        status: response.status,
        code: payload?.error?.code ?? null,
        details: payload?.error?.details ?? {},
      },
    );
  } catch (error) {
    if (error instanceof AgentRequestError) {
      throw error;
    }
    if (error instanceof Error && error.name === "AbortError") {
      throw new AgentRequestError("Request timed out mutating agent data.", {
        status: 0,
        code: "request_timeout",
      });
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeoutId);
  }
}

export function getEventStreamUrl(): string {
  return `${getRequiredApiBaseUrl()}/api/v1/events/stream`;
}

export function getLatestAgentRunsQueryKey() {
  return ["agents", "latest-runs"] as const;
}

export function getAgentRunsQueryKey(params: AgentRunListParams) {
  return [
    "agents",
    "runs",
    params.agent_name ?? "all",
    params.status ?? "all",
    params.since ?? "all",
    params.until ?? "all",
    params.limit ?? DEFAULT_RUN_LIMIT,
  ] as const;
}

export function getAgentRunDetailQueryKey(runId: number) {
  return ["agents", "runs", "detail", runId] as const;
}

export function getSystemEventsQueryKey(params: SystemEventListParams) {
  return [
    "agents",
    "events",
    params.agent_name ?? "all",
    params.event_type ?? "all",
    params.severity ?? "all",
    params.since ?? "all",
    params.until ?? "all",
    params.limit ?? DEFAULT_EVENT_LIMIT,
  ] as const;
}

export function getAgentPauseStatesQueryKey() {
  return ["agents", "pause-states"] as const;
}

export function getFailureEventsQueryKey(params: FailureEventListParams = {}) {
  return [
    "agents",
    "failure-events",
    params.agent_name ?? "all",
    params.classification ?? "all",
    params.severity ?? "all",
    params.since ?? "all",
    params.limit ?? DEFAULT_EVENT_LIMIT,
  ] as const;
}

export function getAgentConfigQueryKey(agentName: AgentName) {
  return ["agents", "config", agentName] as const;
}

export function getBackfillTimelineQueryKey() {
  return ["agents", "backfill", "timeline"] as const;
}

export function getArtifactStorageStatusQueryKey() {
  return ["agents", "artifacts", "status"] as const;
}

export function sortAgentStatusEntries(entries: AgentStatusEntry[]): AgentStatusEntry[] {
  return [...entries].sort(
    (left, right) =>
      AGENT_DISPLAY_ORDER.indexOf(left.agent_name) - AGENT_DISPLAY_ORDER.indexOf(right.agent_name),
  );
}

export async function fetchLatestAgentRuns(): Promise<AgentLatestRunsResponse> {
  const response = parseExpectedResponse(
    await requestJson<unknown>("/api/v1/agents/runs/latest"),
    isAgentLatestRunsResponse,
    "Latest agent runs response has unexpected shape",
    "latest_runs_shape_invalid",
  );
  return { agents: sortAgentStatusEntries(response.agents) };
}

export async function fetchAgentRuns(
  params: AgentRunListParams = {},
): Promise<AgentRunEvent[]> {
  const limit = validateListLimit(params.limit, DEFAULT_RUN_LIMIT, "agent_runs_limit_invalid");
  return parseExpectedResponse(
    await requestJson<unknown>(
      "/api/v1/agents/runs",
      buildSearchParams({
        agent_name: params.agent_name,
        status: params.status,
        since: params.since,
        until: params.until,
        limit,
      }),
    ),
    (value): value is AgentRunEvent[] => Array.isArray(value) && value.every(isAgentRunEvent),
    "Agent runs response has unexpected shape",
    "agent_runs_shape_invalid",
  );
}

export async function fetchAgentRunDetail(runId: number): Promise<AgentRunDetailResponse> {
  return parseExpectedResponse(
    await requestJson<unknown>(`/api/v1/agents/runs/${runId}`),
    isAgentRunDetailResponse,
    "Agent run detail response has unexpected shape",
    "agent_run_detail_shape_invalid",
  );
}

export async function fetchSystemEvents(
  params: SystemEventListParams = {},
): Promise<SystemEventPayload[]> {
  const limit = validateListLimit(
    params.limit,
    DEFAULT_EVENT_LIMIT,
    "system_events_limit_invalid",
  );
  return parseExpectedResponse(
    await requestJson<unknown>(
      "/api/v1/events",
      buildSearchParams({
        agent_name: params.agent_name,
        event_type: params.event_type,
        severity: params.severity,
        since: params.since,
        until: params.until,
        limit,
      }),
    ),
    (value): value is SystemEventPayload[] =>
      Array.isArray(value) && value.every(isSystemEventPayload),
    "System events response has unexpected shape",
    "system_events_shape_invalid",
  );
}

export async function fetchAgentPauseStates(): Promise<AgentPauseState[]> {
  return parseExpectedResponse(
    await requestJson<unknown>("/api/v1/agents/pause-state"),
    (value): value is AgentPauseState[] =>
      Array.isArray(value) && value.every(isAgentPauseState),
    "Agent pause states response has unexpected shape",
    "agent_pause_states_shape_invalid",
  );
}

export async function fetchFailureEvents(
  params: FailureEventListParams = {},
): Promise<FailureEventPayload[]> {
  const limit = validateListLimit(
    params.limit,
    DEFAULT_EVENT_LIMIT,
    "failure_events_limit_invalid",
  );
  return parseExpectedResponse(
    await requestJson<unknown>(
      "/api/v1/events/failures",
      buildSearchParams({
        agent_name: params.agent_name,
        classification: params.classification,
        severity: params.severity,
        since: params.since,
        limit,
      }),
    ),
    (value): value is FailureEventPayload[] =>
      Array.isArray(value) && value.every(isFailureEventPayload),
    "Failure events response has unexpected shape",
    "failure_events_shape_invalid",
  );
}

export async function pauseAgent(
  agentName: AgentName,
  pauseReason: string,
  resumeCondition: string
): Promise<AgentPauseState> {
  return parseExpectedResponse(
    await mutateJson<unknown>(`/api/v1/agents/${agentName}/pause`, "POST", {
      pause_reason: pauseReason,
      resume_condition: resumeCondition,
    }),
    isAgentPauseState,
    "Pause agent response has unexpected shape",
    "pause_agent_shape_invalid",
  );
}

export async function resumeAgent(agentName: AgentName): Promise<AgentPauseState> {
  return parseExpectedResponse(
    await mutateJson<unknown>(`/api/v1/agents/${agentName}/resume`, "POST"),
    isAgentPauseState,
    "Resume agent response has unexpected shape",
    "resume_agent_shape_invalid",
  );
}

export async function triggerAgentRun(
  agentName: AgentName,
): Promise<AgentManualRunTriggerResponse> {
  return parseExpectedResponse(
    await mutateJson<unknown>(`/api/v1/agents/${agentName}/run`, "POST"),
    isAgentManualRunTriggerResponse,
    "Manual agent trigger response has unexpected shape",
    "manual_agent_trigger_shape_invalid",
  );
}

export async function fetchAgentConfig(agentName: AgentName): Promise<AgentConfigResponse> {
  return parseExpectedResponse(
    await requestJson<unknown>(`/api/v1/agents/${agentName}/config`),
    isAgentConfigResponse,
    "Agent config response has unexpected shape",
    "agent_config_shape_invalid",
  );
}

export async function updateAgentConfig(
  agentName: AgentName,
  values: Record<string, string>,
): Promise<AgentConfigUpdateResponse> {
  return parseExpectedResponse(
    await mutateJson<unknown>(`/api/v1/agents/${agentName}/config`, "PATCH", { values }),
    isAgentConfigUpdateResponse,
    "Agent config update response has unexpected shape",
    "agent_config_update_shape_invalid",
  );
}

export async function fetchBackfillTimeline(): Promise<BackfillTimelineResponse> {
  return parseExpectedResponse(
    await requestJson<unknown>("/api/v1/agents/backfill/timeline"),
    isBackfillTimelineResponse,
    "Backfill timeline response has unexpected shape",
    "backfill_timeline_shape_invalid",
  );
}

export async function updateBackfillTimeline(values: {
  oldest_date_in_window: string;
  newest_boundary_exclusive: string;
}): Promise<BackfillTimelineUpdateResponse> {
  return parseExpectedResponse(
    await mutateJson<unknown>("/api/v1/agents/backfill/timeline", "PATCH", values),
    isBackfillTimelineUpdateResponse,
    "Backfill timeline update response has unexpected shape",
    "backfill_timeline_update_shape_invalid",
  );
}

export async function fetchArtifactStorageStatus(): Promise<ArtifactStorageStatusResponse> {
  return parseExpectedResponse(
    await requestJson<unknown>("/api/v1/agents/artifacts/status"),
    isArtifactStorageStatusResponse,
    "Artifact storage status response has unexpected shape",
    "artifact_storage_status_shape_invalid",
  );
}

// ── Analyst source settings ───────────────────────────────────────────────────

export interface AnalystSourceSettings {
  firehose_enabled: boolean;
  backfill_enabled: boolean;
}

export function getAnalystSourceSettingsQueryKey() {
  return ["agents", "analyst", "source-settings"] as const;
}

export async function fetchAnalystSourceSettings(): Promise<AnalystSourceSettings> {
  const result = await requestJson<unknown>("/api/v1/agents/analyst/source-settings");
  if (
    !result ||
    typeof result !== "object" ||
    typeof (result as AnalystSourceSettings).firehose_enabled !== "boolean" ||
    typeof (result as AnalystSourceSettings).backfill_enabled !== "boolean"
  ) {
    throw new Error("Analyst source settings response has unexpected shape");
  }
  return result as AnalystSourceSettings;
}

export async function updateAnalystSourceSettings(
  settings: AnalystSourceSettings,
): Promise<AnalystSourceSettings> {
  const result = await mutateJson<unknown>("/api/v1/agents/analyst/source-settings", "PUT", settings);
  if (
    !result ||
    typeof result !== "object" ||
    typeof (result as AnalystSourceSettings).firehose_enabled !== "boolean" ||
    typeof (result as AnalystSourceSettings).backfill_enabled !== "boolean"
  ) {
    throw new Error("Analyst source settings update response has unexpected shape");
  }
  return result as AnalystSourceSettings;
}

import { z } from "zod";
import { getRequiredApiBaseUrl } from "./base-url";

const EventSeveritySchema = z.enum(["info", "warning", "error", "critical"]);
const FailureClassificationSchema = z.enum(["retryable", "blocking", "rate_limited"]);
const FailureSeveritySchema = z.enum(["warning", "error", "critical"]);
const AgentRunStatusSchema = z.enum(["running", "completed", "failed", "skipped", "skipped_paused"]);

const CheckpointContextSchema = z.object({
  mode: z.string().nullable(),
  page: z.number().nullable(),
  anchor_date: z.string().nullable(),
  window_start: z.string().nullable(),
  window_end: z.string().nullable(),
  resume_required: z.boolean().nullable(),
});

const RoutingContextSchema = z.object({
  session_id: z.string().nullable(),
  route_key: z.string().nullable(),
  agent_key: z.string().nullable(),
});

export const IncidentSchema = z.object({
  id: z.number(),
  event_type: z.string(),
  agent_name: z.string(),
  severity: EventSeveritySchema,
  message: z.string(),
  created_at: z.string(),
  failure_classification: FailureClassificationSchema.nullable(),
  failure_severity: FailureSeveritySchema.nullable(),
  http_status_code: z.number().nullable(),
  retry_after_seconds: z.number().nullable(),
  upstream_provider: z.string().nullable(),
  agent_run_id: z.number().nullable(),
  run_status: AgentRunStatusSchema.nullable(),
  run_started_at: z.string().nullable(),
  run_completed_at: z.string().nullable(),
  run_duration_seconds: z.number().nullable(),
  run_error_summary: z.string().nullable(),
  run_error_context: z.string().nullable(),
  affected_repository_id: z.number().nullable(),
  repository_full_name: z.string().nullable(),
  is_paused: z.boolean(),
  pause_reason: z.string().nullable(),
  resume_condition: z.string().nullable(),
  checkpoint_context: CheckpointContextSchema.nullable(),
  routing_context: RoutingContextSchema.nullable(),
  context: z.record(z.string(), z.unknown()).nullable(),
  next_action: z.string().nullable(),
});

export type Incident = z.infer<typeof IncidentSchema>;

export interface IncidentListParams {
  agent_name?: string;
  severity?: string;
  classification?: string;
  event_type?: string;
  since?: string;
  limit?: number;
}

export async function fetchIncidents(params?: IncidentListParams): Promise<Incident[]> {
  const searchParams = new URLSearchParams();
  if (params?.agent_name) searchParams.set("agent_name", params.agent_name);
  if (params?.severity) searchParams.set("severity", params.severity);
  if (params?.classification) searchParams.set("classification", params.classification);
  if (params?.event_type) searchParams.set("event_type", params.event_type);
  if (params?.since) searchParams.set("since", params.since);
  if (params?.limit) searchParams.set("limit", params.limit.toString());

  const baseUrl = getRequiredApiBaseUrl();
  const url = `${baseUrl}/api/v1/incidents${searchParams.toString() ? `?${searchParams}` : ""}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch incidents: ${response.statusText}`);
  }
  const data = await response.json();
  return z.array(IncidentSchema).parse(data);
}

export async function fetchIncident(incidentId: number): Promise<Incident> {
  const baseUrl = getRequiredApiBaseUrl();
  const response = await fetch(`${baseUrl}/api/v1/incidents/${incidentId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch incident: ${response.statusText}`);
  }
  const data = await response.json();
  return IncidentSchema.parse(data);
}

export function getIncidentsQueryKey(params?: IncidentListParams) {
  return ["incidents", params] as const;
}

export function getIncidentDetailQueryKey(incidentId: number) {
  return ["incidents", incidentId] as const;
}

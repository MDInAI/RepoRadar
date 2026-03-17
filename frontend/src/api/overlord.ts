import { getRequiredApiBaseUrl } from "./base-url";
import type { EventSeverity } from "./agents";

export type OverlordSystemStatus =
  | "healthy"
  | "degraded"
  | "blocked"
  | "rate-limited"
  | "operator-required"
  | "auto-recovering"
  | "stale-state-mismatch";

export interface OverlordIncident {
  incident_key: string;
  title: string;
  status: "active" | "resolved";
  system_status: OverlordSystemStatus;
  severity: EventSeverity;
  summary: string;
  agent_name: string | null;
  provider: string | null;
  detected_at: string | null;
  last_observed_at: string | null;
  retry_after_seconds: number | null;
  requires_operator: boolean;
  auto_recovering: boolean;
  why_it_happened: string;
  what_overlord_did: string | null;
  operator_action: string | null;
}

export interface OverlordActionRecord {
  action: string;
  target: string;
  summary: string;
  created_at: string | null;
  status: "applied" | "skipped" | "resolved";
}

export interface OverlordTelegramStatus {
  enabled: boolean;
  min_severity: EventSeverity;
  daily_digest_enabled: boolean;
  configured_chat: boolean;
  configured_token: boolean;
}

export interface OverlordSummaryResponse {
  agent_name: "overlord";
  display_name: "Overlord";
  status: OverlordSystemStatus;
  headline: string;
  summary: string;
  generated_at: string;
  incidents: OverlordIncident[];
  recent_actions: OverlordActionRecord[];
  operator_todos: string[];
  telemetry: Record<string, string | number | boolean | null>;
  telegram: OverlordTelegramStatus;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isOverlordSummaryResponse(value: unknown): value is OverlordSummaryResponse {
  return (
    isRecord(value) &&
    value.agent_name === "overlord" &&
    typeof value.display_name === "string" &&
    typeof value.status === "string" &&
    typeof value.headline === "string" &&
    typeof value.summary === "string" &&
    Array.isArray(value.incidents) &&
    Array.isArray(value.recent_actions) &&
    Array.isArray(value.operator_todos) &&
    isRecord(value.telemetry) &&
    isRecord(value.telegram)
  );
}

export function getOverlordSummaryQueryKey() {
  return ["overlord", "summary"] as const;
}

export async function fetchOverlordSummary(): Promise<OverlordSummaryResponse> {
  const response = await fetch(`${getRequiredApiBaseUrl()}/api/v1/overlord/summary`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch Overlord summary: ${response.status} ${response.statusText}`);
  }
  const data: unknown = await response.json();
  if (!isOverlordSummaryResponse(data)) {
    throw new Error("Overlord summary response has unexpected shape");
  }
  return data;
}

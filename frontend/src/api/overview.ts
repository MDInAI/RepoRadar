import { getRequiredApiBaseUrl } from "./base-url";

export interface OverviewSummary {
  ingestion: {
    total_repositories: number;
    pending_intake: number;
    firehose_discovered: number;
    backfill_discovered: number;
  };
  triage: {
    pending: number;
    accepted: number;
    rejected: number;
  };
  analysis: {
    pending: number;
    in_progress: number;
    completed: number;
    failed: number;
  };
  backlog: {
    queue_pending: number;
    queue_in_progress: number;
    queue_completed: number;
    queue_failed: number;
    triage_pending: number;
    triage_accepted: number;
    triage_rejected: number;
    analysis_pending: number;
    analysis_in_progress: number;
    analysis_completed: number;
    analysis_failed: number;
  };
  agents: Array<{
    agent_name: string;
    status: string | null;
    is_paused: boolean;
    last_run_at: string | null;
  }>;
  failures: {
    total_failures: number;
    critical_failures: number;
    rate_limited_failures: number;
    blocking_failures: number;
  };
}

export async function fetchOverviewSummary(): Promise<OverviewSummary> {
  const response = await fetch(`${getRequiredApiBaseUrl()}/api/v1/overview/summary`, {
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch overview summary: ${response.statusText}`);
  }
  return response.json();
}

export function getOverviewSummaryQueryKey() {
  return ["overview", "summary"];
}

import { getRequiredApiBaseUrl } from "./base-url";

export interface SynthesisRun {
  id: number;
  idea_family_id: number | null;
  run_type: string;
  status: string;
  input_repository_ids: number[];
  output_text: string | null;
  title: string | null;
  summary: string | null;
  key_insights: string[] | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface TriggerCombinerRequest {
  idea_family_id?: number | null;
  repository_ids?: number[] | null;
}

const getBaseUrl = () => `${getRequiredApiBaseUrl()}/api/v1/synthesis`;

export async function triggerCombiner(data: TriggerCombinerRequest): Promise<SynthesisRun> {
  const response = await fetch(`${getBaseUrl()}/combiner`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(`Failed to trigger combiner: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchSynthesisRuns(
  familyId?: number | null,
  filters?: {
    status?: string;
    search?: string;
    dateFrom?: string;
    dateTo?: string;
    repositoryId?: number;
  }
): Promise<SynthesisRun[]> {
  const params = new URLSearchParams();
  if (familyId) params.append("idea_family_id", familyId.toString());
  if (filters?.status) params.append("status", filters.status);
  if (filters?.search) params.append("search", filters.search);
  if (filters?.dateFrom) params.append("date_from", filters.dateFrom);
  if (filters?.dateTo) params.append("date_to", filters.dateTo);
  if (filters?.repositoryId) params.append("repository_id", filters.repositoryId.toString());

  const url = `${getBaseUrl()}/runs${params.toString() ? `?${params.toString()}` : ""}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch synthesis runs: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchSynthesisRun(runId: number): Promise<SynthesisRun> {
  const response = await fetch(`${getBaseUrl()}/runs/${runId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch synthesis run: ${response.statusText}`);
  }
  return response.json();
}

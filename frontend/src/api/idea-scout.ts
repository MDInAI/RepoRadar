import { getRequiredApiBaseUrl } from "./base-url";

export type IdeaSearchDirection = "backward" | "forward";
export type IdeaSearchStatus = "active" | "paused" | "completed" | "cancelled";

export interface IdeaSearchResponse {
  id: number;
  idea_text: string;
  search_queries: string[];
  direction: IdeaSearchDirection;
  status: IdeaSearchStatus;
  obsession_context_id: number | null;
  total_repos_found: number;
  created_at: string;
  updated_at: string;
}

export interface IdeaSearchProgressSummary {
  query_index: number;
  window_start_date: string;
  created_before_boundary: string;
  exhausted: boolean;
  resume_required: boolean;
  next_page: number;
  pages_processed_in_run: number;
  last_checkpointed_at: string | null;
}

export interface IdeaSearchDetailResponse extends IdeaSearchResponse {
  progress: IdeaSearchProgressSummary[];
  discovery_count: number;
}

export interface DiscoveredRepo {
  github_repository_id: number;
  full_name: string;
  description: string | null;
  stargazers_count: number;
  discovered_at: string;
}

const base = () => `${getRequiredApiBaseUrl()}/api/v1/idea-scout`;

export async function createIdeaSearch(data: {
  idea_text: string;
  direction?: IdeaSearchDirection;
}): Promise<IdeaSearchResponse> {
  const res = await fetch(`${base()}/searches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchIdeaSearches(params?: {
  status?: IdeaSearchStatus;
  direction?: IdeaSearchDirection;
}): Promise<IdeaSearchResponse[]> {
  const url = new URL(`${base()}/searches`);
  if (params?.status) url.searchParams.set("status", params.status);
  if (params?.direction) url.searchParams.set("direction", params.direction);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchIdeaSearch(
  searchId: number
): Promise<IdeaSearchDetailResponse> {
  const res = await fetch(`${base()}/searches/${searchId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function pauseIdeaSearch(
  searchId: number
): Promise<IdeaSearchResponse> {
  const res = await fetch(`${base()}/searches/${searchId}/pause`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function resumeIdeaSearch(
  searchId: number
): Promise<IdeaSearchResponse> {
  const res = await fetch(`${base()}/searches/${searchId}/resume`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function cancelIdeaSearch(
  searchId: number
): Promise<IdeaSearchResponse> {
  const res = await fetch(`${base()}/searches/${searchId}/cancel`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateIdeaSearch(
  searchId: number,
  data: { search_queries: string[] }
): Promise<IdeaSearchResponse> {
  const res = await fetch(`${base()}/searches/${searchId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchIdeaSearchDiscoveries(
  searchId: number,
  params?: { limit?: number; offset?: number }
): Promise<DiscoveredRepo[]> {
  const url = new URL(`${base()}/searches/${searchId}/discoveries`);
  if (params?.limit) url.searchParams.set("limit", String(params.limit));
  if (params?.offset) url.searchParams.set("offset", String(params.offset));
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

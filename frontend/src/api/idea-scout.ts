import { getRequiredApiBaseUrl } from "./base-url";

export type IdeaSearchDirection = "backward" | "forward";
export type IdeaSearchStatus = "active" | "paused" | "completed" | "cancelled";

interface IdeaScoutErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
  };
}

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
  consecutive_errors: number;
  last_error: string | null;
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

function buildIdeaScoutNetworkErrorMessage(action: string): string {
  return `${action} failed because the backend API could not be reached at ${getRequiredApiBaseUrl()}. Make sure the backend server is running and NEXT_PUBLIC_API_URL is correct.`;
}

function isIdeaScoutErrorEnvelope(payload: unknown): payload is IdeaScoutErrorEnvelope {
  if (!payload || typeof payload !== "object") {
    return false;
  }

  const maybeError = (payload as IdeaScoutErrorEnvelope).error;
  return !maybeError || typeof maybeError.message === "string" || typeof maybeError.code === "string";
}

async function parseIdeaScoutError(response: Response): Promise<Error> {
  let payload: IdeaScoutErrorEnvelope | null = null;
  try {
    const raw = (await response.json()) as unknown;
    payload = isIdeaScoutErrorEnvelope(raw) ? raw : null;
  } catch {
    // Fall back to status text below.
  }

  const message =
    payload?.error?.message ||
    response.statusText ||
    `Idea Scout request failed with status ${response.status}`;

  return new Error(message);
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(input, init);
  } catch {
    throw new Error(buildIdeaScoutNetworkErrorMessage("Idea Scout request"));
  }
  if (!res.ok) {
    throw await parseIdeaScoutError(res);
  }
  return res.json() as Promise<T>;
}

export async function createIdeaSearch(data: {
  idea_text: string;
  direction?: IdeaSearchDirection;
}): Promise<IdeaSearchResponse> {
  return requestJson<IdeaSearchResponse>(`${base()}/searches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function fetchIdeaSearches(params?: {
  status?: IdeaSearchStatus;
  direction?: IdeaSearchDirection;
}): Promise<IdeaSearchResponse[]> {
  const url = new URL(`${base()}/searches`);
  if (params?.status) {
    url.searchParams.set("status", params.status);
  }
  if (params?.direction) {
    url.searchParams.set("direction", params.direction);
  }
  return requestJson<IdeaSearchResponse[]>(url.toString());
}

export async function fetchIdeaSearch(searchId: number): Promise<IdeaSearchDetailResponse> {
  return requestJson<IdeaSearchDetailResponse>(`${base()}/searches/${searchId}`);
}

export async function pauseIdeaSearch(searchId: number): Promise<IdeaSearchResponse> {
  return requestJson<IdeaSearchResponse>(`${base()}/searches/${searchId}/pause`, {
    method: "POST",
  });
}

export async function resumeIdeaSearch(searchId: number): Promise<IdeaSearchResponse> {
  return requestJson<IdeaSearchResponse>(`${base()}/searches/${searchId}/resume`, {
    method: "POST",
  });
}

export async function cancelIdeaSearch(searchId: number): Promise<IdeaSearchResponse> {
  return requestJson<IdeaSearchResponse>(`${base()}/searches/${searchId}/cancel`, {
    method: "POST",
  });
}

export async function updateIdeaSearch(
  searchId: number,
  data: { search_queries: string[] }
): Promise<IdeaSearchResponse> {
  return requestJson<IdeaSearchResponse>(`${base()}/searches/${searchId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function fetchIdeaSearchDiscoveries(
  searchId: number,
  params?: { limit?: number; offset?: number }
): Promise<DiscoveredRepo[]> {
  const url = new URL(`${base()}/searches/${searchId}/discoveries`);
  if (params?.limit) {
    url.searchParams.set("limit", String(params.limit));
  }
  if (params?.offset) {
    url.searchParams.set("offset", String(params.offset));
  }
  return requestJson<DiscoveredRepo[]>(url.toString());
}

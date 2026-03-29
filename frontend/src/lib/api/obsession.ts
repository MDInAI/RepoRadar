import { apiClient } from './client';

export interface SynthesisRunSummary {
  id: number;
  run_type: string;
  status: string;
  title: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface ObsessionContextResponse {
  id: number;
  idea_family_id: number | null;
  synthesis_run_id: number | null;
  idea_search_id: number | null;
  idea_text: string | null;
  title: string;
  description: string | null;
  status: string;
  refresh_policy: string;
  last_refresh_at: string | null;
  synthesis_run_count: number;
  created_at: string;
  updated_at: string;
}

export interface RepositorySummary {
  id: number;
  full_name: string;
  stars: number;
}

export interface ObsessionContextDetailResponse {
  id: number;
  idea_family_id: number | null;
  synthesis_run_id: number | null;
  idea_search_id: number | null;
  idea_text: string | null;
  title: string;
  description: string | null;
  status: string;
  refresh_policy: string;
  last_refresh_at: string | null;
  synthesis_runs: SynthesisRunSummary[];
  family_title: string | null;
  repository_count: number;
  repositories: RepositorySummary[];
  scope_updated_at: string | null;
  memory_segment_count: number;
  created_at: string;
  updated_at: string;
}

export interface ObsessionContextCreateRequest {
  idea_family_id?: number | null;
  synthesis_run_id?: number | null;
  idea_search_id?: number | null;
  idea_text?: string | null;
  title: string;
  description?: string | null;
  refresh_policy?: string;
}

export interface ObsessionContextUpdateRequest {
  title?: string | null;
  description?: string | null;
  status?: string | null;
  refresh_policy?: string | null;
}

export const obsessionApi = {
  createContext: async (data: ObsessionContextCreateRequest): Promise<ObsessionContextResponse> => {
    const response = await apiClient.post<ObsessionContextResponse>('/obsession/contexts', data);
    return response.data;
  },

  listContexts: async (params?: {
    idea_family_id?: number;
    status?: string;
  }): Promise<ObsessionContextResponse[]> => {
    const response = await apiClient.get<ObsessionContextResponse[]>('/obsession/contexts', { params });
    return response.data;
  },

  getContext: async (contextId: number): Promise<ObsessionContextDetailResponse> => {
    const response = await apiClient.get<ObsessionContextDetailResponse>(`/obsession/contexts/${contextId}`);
    return response.data;
  },

  updateContext: async (
    contextId: number,
    data: ObsessionContextUpdateRequest
  ): Promise<ObsessionContextResponse> => {
    const response = await apiClient.put<ObsessionContextResponse>(`/obsession/contexts/${contextId}`, data);
    return response.data;
  },

  triggerRefresh: async (contextId: number): Promise<{ synthesis_run_id: number }> => {
    const response = await apiClient.post<{ synthesis_run_id: number }>(`/obsession/contexts/${contextId}/refresh`);
    return response.data;
  },
};

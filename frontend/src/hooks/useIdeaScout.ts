import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createIdeaSearch,
  fetchIdeaSearches,
  fetchIdeaSearch,
  pauseIdeaSearch,
  resumeIdeaSearch,
  cancelIdeaSearch,
  updateIdeaSearch,
  fetchIdeaSearchDiscoveries,
  enableAnalystForSearch,
  disableAnalystForSearch,
  type IdeaSearchDirection,
  type IdeaSearchStatus,
} from "@/api/idea-scout";

export const useIdeaSearches = (params?: {
  status?: IdeaSearchStatus;
  direction?: IdeaSearchDirection;
}) => {
  return useQuery({
    queryKey: ["idea-searches", params?.status, params?.direction],
    queryFn: () => fetchIdeaSearches(params),
  });
};

export const useIdeaSearch = (searchId: number) => {
  return useQuery({
    queryKey: ["idea-search", searchId],
    queryFn: () => fetchIdeaSearch(searchId),
    enabled: !!searchId,
    refetchInterval: (query) => {
      const data = query.state.data;
      // Poll if scouting is active OR if analyst is enabled and has repos left to analyze
      if (data?.status === "active") return 15_000;
      if (data?.analyst_enabled && (data.analyzed_count ?? 0) < data.discovery_count) return 20_000;
      return false;
    },
  });
};

export const useIdeaSearchDiscoveries = (
  searchId: number,
  params?: { limit?: number; offset?: number }
) => {
  return useQuery({
    queryKey: ["idea-search-discoveries", searchId, params?.limit, params?.offset],
    queryFn: () => fetchIdeaSearchDiscoveries(searchId, params),
    enabled: !!searchId,
  });
};

export const useCreateIdeaSearch = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { idea_text: string; direction?: IdeaSearchDirection }) =>
      createIdeaSearch(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["idea-searches"] });
    },
  });
};

export const usePauseIdeaSearch = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (searchId: number) => pauseIdeaSearch(searchId),
    onSuccess: (_data, searchId) => {
      queryClient.invalidateQueries({ queryKey: ["idea-search", searchId] });
      queryClient.invalidateQueries({ queryKey: ["idea-searches"] });
    },
  });
};

export const useResumeIdeaSearch = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (searchId: number) => resumeIdeaSearch(searchId),
    onSuccess: (_data, searchId) => {
      queryClient.invalidateQueries({ queryKey: ["idea-search", searchId] });
      queryClient.invalidateQueries({ queryKey: ["idea-searches"] });
    },
  });
};

export const useCancelIdeaSearch = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (searchId: number) => cancelIdeaSearch(searchId),
    onSuccess: (_data, searchId) => {
      queryClient.invalidateQueries({ queryKey: ["idea-search", searchId] });
      queryClient.invalidateQueries({ queryKey: ["idea-searches"] });
    },
  });
};

export const useSetAnalystEnabled = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ searchId, enabled }: { searchId: number; enabled: boolean }) =>
      enabled ? enableAnalystForSearch(searchId) : disableAnalystForSearch(searchId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["idea-search", variables.searchId] });
      queryClient.invalidateQueries({ queryKey: ["idea-searches"] });
    },
  });
};

export const useUpdateIdeaSearch = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ searchId, data }: { searchId: number; data: { search_queries: string[] } }) =>
      updateIdeaSearch(searchId, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["idea-search", variables.searchId] });
      queryClient.invalidateQueries({ queryKey: ["idea-searches"] });
    },
  });
};

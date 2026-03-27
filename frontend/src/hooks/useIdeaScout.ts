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
      const status = query.state.data?.status;
      return status === "active" ? 15_000 : false;
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

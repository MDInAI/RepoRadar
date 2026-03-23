import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { obsessionApi, ObsessionContextCreateRequest, ObsessionContextUpdateRequest } from '@/lib/api/obsession';

export const useObsessionContexts = (ideaFamilyId?: number, status?: string) => {
  return useQuery({
    queryKey: ['obsession-contexts', ideaFamilyId, status],
    queryFn: () => obsessionApi.listContexts({ idea_family_id: ideaFamilyId, status }),
  });
};

export const useObsessionContext = (contextId: number) => {
  return useQuery({
    queryKey: ['obsession-context', contextId],
    queryFn: () => obsessionApi.getContext(contextId),
    enabled: !!contextId,
  });
};

export const useCreateObsessionContext = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ObsessionContextCreateRequest) => obsessionApi.createContext(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['obsession-contexts'] });
    },
  });
};

export const useUpdateObsessionContext = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ contextId, data }: { contextId: number; data: ObsessionContextUpdateRequest }) =>
      obsessionApi.updateContext(contextId, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['obsession-context', variables.contextId] });
      queryClient.invalidateQueries({ queryKey: ['obsession-contexts'] });
    },
  });
};

export const useTriggerRefresh = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (contextId: number) => obsessionApi.triggerRefresh(contextId),
    onSuccess: (_data, contextId) => {
      queryClient.invalidateQueries({ queryKey: ['obsession-context', contextId] });
      queryClient.invalidateQueries({ queryKey: ['synthesis-runs'] });
    },
  });
};

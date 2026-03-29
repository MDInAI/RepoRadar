import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchLatestAgentRuns,
  fetchAgentRuns,
  fetchSystemEvents,
  fetchAgentPauseStates,
  resumeAgent,
  fetchAnalystSourceSettings,
  updateAnalystSourceSettings,
  getLatestAgentRunsQueryKey,
  getAgentRunsQueryKey,
  getSystemEventsQueryKey,
  getAgentPauseStatesQueryKey,
  getAnalystSourceSettingsQueryKey,
  type AnalystSourceSettings,
} from "@/api/agents";

export const useIdeaScoutWorkerStatus = () => {
  return useQuery({
    queryKey: getLatestAgentRunsQueryKey(),
    queryFn: fetchLatestAgentRuns,
    refetchInterval: 30_000,
    select: (data) => data.agents.find((a) => a.agent_name === "idea_scout") ?? null,
  });
};

export const useIdeaScoutWorkerRuns = (limit = 8, enabled = true) => {
  return useQuery({
    queryKey: getAgentRunsQueryKey({ agent_name: "idea_scout", limit }),
    queryFn: () => fetchAgentRuns({ agent_name: "idea_scout", limit }),
    enabled,
    refetchInterval: 20_000,
  });
};

export const useIdeaScoutWorkerEvents = (limit = 12, enabled = true) => {
  return useQuery({
    queryKey: getSystemEventsQueryKey({ agent_name: "idea_scout", limit }),
    queryFn: () => fetchSystemEvents({ agent_name: "idea_scout", limit }),
    enabled,
    refetchInterval: 20_000,
  });
};

export const useAnalystPauseState = () => {
  return useQuery({
    queryKey: getAgentPauseStatesQueryKey(),
    queryFn: fetchAgentPauseStates,
    refetchInterval: 15_000,
    select: (states) => states.find((s) => s.agent_name === "analyst") ?? null,
  });
};

export const useAnalystLiveStatus = () => {
  return useQuery({
    queryKey: getLatestAgentRunsQueryKey(),
    queryFn: fetchLatestAgentRuns,
    refetchInterval: 10_000,
    select: (data) => data.agents.find((a) => a.agent_name === "analyst") ?? null,
  });
};

export const useResumeAnalyst = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => resumeAgent("analyst"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: getAgentPauseStatesQueryKey() });
      queryClient.invalidateQueries({ queryKey: getLatestAgentRunsQueryKey() });
    },
  });
};

export const useAnalystSourceSettings = () => {
  return useQuery({
    queryKey: getAnalystSourceSettingsQueryKey(),
    queryFn: fetchAnalystSourceSettings,
  });
};

export const useUpdateAnalystSourceSettings = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (settings: AnalystSourceSettings) => updateAnalystSourceSettings(settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: getAnalystSourceSettingsQueryKey() });
    },
  });
};

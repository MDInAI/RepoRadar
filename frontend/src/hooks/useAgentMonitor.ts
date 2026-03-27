import { useQuery } from "@tanstack/react-query";
import {
  fetchLatestAgentRuns,
  fetchAgentRuns,
  fetchSystemEvents,
  getLatestAgentRunsQueryKey,
  getAgentRunsQueryKey,
  getSystemEventsQueryKey,
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

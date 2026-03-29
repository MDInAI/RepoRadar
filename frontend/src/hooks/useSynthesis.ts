import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchSynthesisRuns,
  fetchSynthesisRun,
  triggerCombiner,
  triggerDeepSynthesis,
  type SynthesisRun,
  type TriggerCombinerRequest,
} from "@/api/synthesis";

export function useSynthesisRuns(
  familyId?: number | null,
  filters?: {
    status?: string;
    search?: string;
    dateFrom?: string;
    dateTo?: string;
    repositoryId?: number;
  }
) {
  return useQuery({
    queryKey: ["synthesis-runs", familyId, filters],
    queryFn: () => fetchSynthesisRuns(familyId, filters),
  });
}

export function useSynthesisRun(runId: number | null | undefined) {
  return useQuery({
    queryKey: ["synthesis-run", runId],
    queryFn: () => fetchSynthesisRun(runId as number),
    enabled: typeof runId === "number",
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "running" ? 2000 : false;
    },
  });
}

export function useTriggerCombiner() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: TriggerCombinerRequest) => triggerCombiner(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["synthesis-runs"] });
    },
  });
}

export function useTriggerDeepSynthesis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (familyId: number) => triggerDeepSynthesis(familyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["synthesis-runs"] });
    },
  });
}

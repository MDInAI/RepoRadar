"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { resumeAgent, getAgentPauseStatesQueryKey, type AgentName } from "@/api/agents";

export function ResumeAgentButton({ agentName }: { agentName: AgentName }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => resumeAgent(agentName),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: getAgentPauseStatesQueryKey() });
      void queryClient.invalidateQueries({ queryKey: ["agents", "latest-runs"] });
      void queryClient.invalidateQueries({ queryKey: ["agents", "events"] });
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  return (
    <div className="mt-3">
      <button
        onClick={() => mutation.mutate()}
        disabled={mutation.isPending}
        className="rounded-full border border-orange-300 bg-orange-50 px-4 py-2 text-sm font-semibold text-orange-900 transition hover:bg-orange-100 disabled:opacity-50"
      >
        {mutation.isPending ? "Resuming..." : "Resume Agent"}
      </button>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      {mutation.isSuccess && <p className="mt-2 text-sm text-green-600">Agent resumed successfully</p>}
    </div>
  );
}

"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { pauseAgent, getAgentPauseStatesQueryKey, type AgentName } from "@/api/agents";

export function PauseAgentButton({ agentName }: { agentName: AgentName }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [pauseReason, setPauseReason] = useState("");
  const [resumeCondition, setResumeCondition] = useState("");

  const mutation = useMutation({
    mutationFn: ({ reason, condition }: { reason: string; condition: string }) =>
      pauseAgent(agentName, reason, condition),
    onSuccess: () => {
      setError(null);
      setShowModal(false);
      setPauseReason("");
      setResumeCondition("");
      void queryClient.invalidateQueries({ queryKey: getAgentPauseStatesQueryKey() });
      void queryClient.invalidateQueries({ queryKey: ["agents", "latest-runs"] });
      void queryClient.invalidateQueries({ queryKey: ["agents", "events"] });
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!pauseReason.trim() || !resumeCondition.trim()) {
      setError("Both fields are required");
      return;
    }
    mutation.mutate({ reason: pauseReason, condition: resumeCondition });
  };

  return (
    <>
      <div className="mt-3">
        <button
          onClick={() => setShowModal(true)}
          disabled={mutation.isPending}
          className="rounded-full border border-slate-300 bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-900 transition hover:bg-slate-100 disabled:opacity-50"
        >
          Pause Agent
        </button>
        {mutation.isSuccess && <p className="mt-2 text-sm text-green-600">Agent paused successfully</p>}
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-semibold text-slate-900">Pause {agentName}</h2>
            <form onSubmit={handleSubmit}>
              <div className="mb-4">
                <label htmlFor="pauseReason" className="mb-1 block text-sm font-medium text-slate-700">
                  Reason for pause
                </label>
                <input
                  id="pauseReason"
                  type="text"
                  value={pauseReason}
                  onChange={(e) => setPauseReason(e.target.value)}
                  className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
                  placeholder="e.g., Rate limit detected"
                  autoFocus
                />
              </div>
              <div className="mb-4">
                <label htmlFor="resumeCondition" className="mb-1 block text-sm font-medium text-slate-700">
                  Resume condition
                </label>
                <input
                  id="resumeCondition"
                  type="text"
                  value={resumeCondition}
                  onChange={(e) => setResumeCondition(e.target.value)}
                  className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
                  placeholder="e.g., Wait 1 hour for rate limit reset"
                />
              </div>
              {error && <p className="mb-4 text-sm text-red-600">{error}</p>}
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setShowModal(false);
                    setError(null);
                  }}
                  className="rounded border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={mutation.isPending}
                  className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
                >
                  {mutation.isPending ? "Pausing..." : "Pause Agent"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}

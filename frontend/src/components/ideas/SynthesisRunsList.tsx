"use client";

import { useSynthesisRuns } from "@/hooks/useSynthesis";
import { useState } from "react";
import { SynthesisRunDetailDialog } from "./SynthesisRunDetailDialog";

interface SynthesisRunsListProps {
  familyId: number | null;
}

export function SynthesisRunsList({ familyId }: SynthesisRunsListProps) {
  const { data: runs, isLoading } = useSynthesisRuns(familyId);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);

  if (isLoading) {
    return <div className="p-4 text-sm text-neutral-500">Loading synthesis runs...</div>;
  }

  if (!runs || runs.length === 0) {
    return <div className="p-4 text-sm text-neutral-500">No synthesis runs yet.</div>;
  }

  return (
    <>
      <div className="divide-y divide-neutral-800">
        {runs.map((run) => (
          <div key={run.id} className="p-4 hover:bg-neutral-900/50">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">Run #{run.id}</span>
                <span
                  className={`px-2 py-0.5 rounded text-xs ${
                    run.status === "completed"
                      ? "bg-green-900/30 text-green-400"
                      : run.status === "failed"
                      ? "bg-red-900/30 text-red-400"
                      : run.status === "running"
                      ? "bg-blue-900/30 text-blue-400"
                      : "bg-neutral-800 text-neutral-400"
                  }`}
                >
                  {run.status}
                </span>
              </div>
              <span className="text-xs text-neutral-500">
                {run.input_repository_ids.length} repos
              </span>
            </div>
            {run.status === "completed" && run.output_text && (
              <p className="text-sm text-neutral-400 mb-2 line-clamp-2">{run.output_text}</p>
            )}
            {run.status === "failed" && run.error_message && (
              <p className="text-sm text-red-400 mb-2 line-clamp-1">{run.error_message}</p>
            )}
            <div className="flex items-center justify-between">
              <span className="text-xs text-neutral-600">
                {new Date(run.created_at).toLocaleString()}
              </span>
              <button
                onClick={() => setSelectedRunId(run.id)}
                className="text-xs text-blue-400 hover:text-blue-300"
              >
                View Details
              </button>
            </div>
          </div>
        ))}
      </div>

      {selectedRunId && (
        <SynthesisRunDetailDialog runId={selectedRunId} onClose={() => setSelectedRunId(null)} />
      )}
    </>
  );
}

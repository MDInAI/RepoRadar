"use client";

import { useSynthesisRuns } from "@/hooks/useSynthesis";
import { useState, useEffect } from "react";
import { formatAppDateTime } from "@/lib/time";
import { SynthesisRunDetailDialog } from "./SynthesisRunDetailDialog";
import { SynthesisComparisonView } from "./SynthesisComparisonView";

interface SynthesisHistoryPanelProps {
  familyId: number;
}

export function SynthesisHistoryPanel({ familyId }: SynthesisHistoryPanelProps) {
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [repoFilter, setRepoFilter] = useState("");
  const [selectedForComparison, setSelectedForComparison] = useState<number[]>([]);
  const [showComparison, setShowComparison] = useState(false);

  // Clear comparison state when family changes
  useEffect(() => {
    setSelectedForComparison([]);
    setShowComparison(false);
  }, [familyId]);

  // Use server-side filtering with UTC date conversion
  const filters = {
    status: statusFilter !== "all" ? statusFilter : undefined,
    search: searchQuery || undefined,
    dateFrom: dateFrom ? dateFrom + "T00:00:00Z" : undefined,
    dateTo: dateTo ? dateTo + "T23:59:59Z" : undefined,
    repositoryId: repoFilter ? parseInt(repoFilter, 10) : undefined,
  };

  const { data: runs, isLoading } = useSynthesisRuns(familyId, filters);

  // Group runs by type
  const groupedRuns = (runs || []).reduce((acc, run) => {
    const type = run.run_type || "combiner";
    if (!acc[type]) acc[type] = [];
    acc[type].push(run);
    return acc;
  }, {} as Record<string, typeof runs>);

  const toggleComparison = (runId: number) => {
    setSelectedForComparison(prev =>
      prev.includes(runId)
        ? prev.filter(id => id !== runId)
        : prev.length < 3 ? [...prev, runId] : prev
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-neutral-300">Synthesis History</h3>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="text-xs bg-neutral-800 border border-neutral-700 rounded px-2 py-1"
        >
          <option value="all">All</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="running">Running</option>
        </select>
      </div>

      <div className="space-y-2">
        <input
          type="text"
          placeholder="Search title, summary, insights..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full text-xs bg-neutral-800 border border-neutral-700 rounded px-2 py-1"
        />
        <div className="flex gap-2">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="flex-1 text-xs bg-neutral-800 border border-neutral-700 rounded px-2 py-1"
            placeholder="From"
          />
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="flex-1 text-xs bg-neutral-800 border border-neutral-700 rounded px-2 py-1"
            placeholder="To"
          />
        </div>
        <input
          type="text"
          placeholder="Filter by repository ID..."
          value={repoFilter}
          onChange={(e) => setRepoFilter(e.target.value)}
          className="w-full text-xs bg-neutral-800 border border-neutral-700 rounded px-2 py-1"
        />
      </div>

      {selectedForComparison.length > 0 && (
        <div className="flex items-center justify-between bg-neutral-800 rounded p-2">
          <span className="text-xs text-neutral-400">
            {selectedForComparison.length} selected for comparison
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setShowComparison(true)}
              disabled={selectedForComparison.length < 2}
              className="text-xs bg-blue-600 hover:bg-blue-700 disabled:bg-neutral-700 disabled:text-neutral-500 text-white px-2 py-1 rounded"
            >
              Compare
            </button>
            <button
              onClick={() => setSelectedForComparison([])}
              className="text-xs text-neutral-400 hover:text-neutral-300"
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="text-sm text-neutral-500">Loading...</div>
      ) : !runs || runs.length === 0 ? (
        <div className="text-sm text-neutral-500">No synthesis runs found</div>
      ) : (
        <div className="space-y-4">
          {Object.entries(groupedRuns).map(([runType, typeRuns]) => (
            <div key={runType}>
              <h4 className="text-xs font-semibold text-neutral-500 uppercase mb-2">
                {runType === "combiner" ? "Combiner Runs" : `${runType} Runs`}
              </h4>
              <div className="space-y-2">
                {(typeRuns || []).map((run) => (
                  <div
                    key={run.id}
                    className={`bg-neutral-900 border rounded p-3 ${
                      selectedForComparison.includes(run.id)
                        ? "border-blue-600"
                        : "border-neutral-800"
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div
                        className="flex-1 cursor-pointer"
                        onClick={() => setSelectedRunId(run.id)}
                      >
                        <div className="text-sm font-medium text-neutral-200">
                          {run.title || `Run #${run.id}`}
                        </div>
                        {run.summary && (
                          <div className="text-xs text-neutral-400 mt-1 line-clamp-2">
                            {run.summary}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-2 ml-2">
                        <input
                          type="checkbox"
                          checked={selectedForComparison.includes(run.id)}
                          onChange={() => toggleComparison(run.id)}
                          className="cursor-pointer"
                        />
                        <span
                          className={`px-2 py-0.5 rounded text-xs ${
                            run.status === "completed"
                              ? "bg-green-900/30 text-green-400"
                              : run.status === "failed"
                              ? "bg-red-900/30 text-red-400"
                              : "bg-neutral-800 text-neutral-400"
                          }`}
                        >
                          {run.status}
                        </span>
                      </div>
                    </div>
                    <div className="text-xs text-neutral-600 mt-2">
                      {formatAppDateTime(run.created_at)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {selectedRunId && (
        <SynthesisRunDetailDialog
          runId={selectedRunId}
          onClose={() => setSelectedRunId(null)}
        />
      )}

      {showComparison && selectedForComparison.length >= 2 && (
        <SynthesisComparisonView
          runIds={selectedForComparison}
          onClose={() => setShowComparison(false)}
        />
      )}
    </div>
  );
}

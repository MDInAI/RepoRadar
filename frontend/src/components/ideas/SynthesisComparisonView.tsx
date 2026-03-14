"use client";

import { useSynthesisRun } from "@/hooks/useSynthesis";
import { useQuery } from "@tanstack/react-query";
import { fetchRepositoryDetail } from "@/api/repositories";

interface SynthesisComparisonViewProps {
  runIds: number[];
  onClose: () => void;
}

export function SynthesisComparisonView({ runIds, onClose }: SynthesisComparisonViewProps) {
  // Call hooks unconditionally at top level (max 3 runs supported)
  const run1 = useSynthesisRun(runIds[0]);
  const run2 = useSynthesisRun(runIds[1]);
  const run3 = useSynthesisRun(runIds[2] ?? null);

  const runs = [run1, run2, run3].slice(0, runIds.length);

  // Fetch all repository details
  const allRepoIds = Array.from(new Set(runs.flatMap(r => r.data?.input_repository_ids || [])));
  const { data: repoDetails } = useQuery({
    queryKey: ["comparison-repos", allRepoIds],
    queryFn: async () => {
      const details = await Promise.all(
        allRepoIds.map(id => fetchRepositoryDetail(id).catch(() => null))
      );
      return Object.fromEntries(allRepoIds.map((id, idx) => [id, details[idx]]));
    },
    enabled: allRepoIds.length > 0,
  });

  const getRepoName = (id: number) => repoDetails?.[id]?.full_name || `#${id}`;

  const getRepoDiff = (runIndex: number) => {
    const currentRun = runs[runIndex].data;
    if (!currentRun) return { unique: [], common: [], missing: [] };

    const currentRepos = new Set(currentRun.input_repository_ids);
    const otherRuns = runs.filter((_, i) => i !== runIndex);

    // Common = repos in current AND all other runs
    const common = Array.from(currentRepos).filter(id =>
      otherRuns.every(r => r.data?.input_repository_ids?.includes(id))
    );

    // Unique = repos only in current run
    const otherRepos = new Set(otherRuns.flatMap(r => r.data?.input_repository_ids || []));
    const unique = Array.from(currentRepos).filter(id => !otherRepos.has(id));

    // Missing = repos in other runs but not current
    const missing = Array.from(otherRepos).filter(id => !currentRepos.has(id));

    return { unique, common, missing };
  };

  const exportComparison = async () => {
    // Check if any run failed to load
    if (runs.some(r => !r.data)) {
      alert("Cannot export: some runs failed to load");
      return;
    }

    const content = runs.map((r, idx) => {
      const run = r.data;
      if (!run) return "";
      const diff = getRepoDiff(idx);
      let repoSection = "**Repositories:**\n";
      if (diff.unique.length > 0) {
        repoSection += `Unique: ${diff.unique.map(id => getRepoName(id)).join(", ")}\n`;
      }
      if (diff.common.length > 0) {
        repoSection += `Common: ${diff.common.map(id => getRepoName(id)).join(", ")}\n`;
      }
      if (diff.missing.length > 0) {
        repoSection += `Missing: ${diff.missing.map(id => getRepoName(id)).join(", ")}\n`;
      }
      return `## Run #${run.id}\n\n**Title:** ${run.title || "N/A"}\n\n**Summary:** ${run.summary || "N/A"}\n\n**Key Insights:**\n${Array.isArray(run.key_insights) ? run.key_insights.map((i: string) => `- ${i}`).join("\n") : "None"}\n\n${repoSection}\n`;
    }).join("\n---\n\n");

    try {
      await navigator.clipboard.writeText(content);
      alert("Comparison copied to clipboard!");
    } catch (err) {
      alert("Failed to copy to clipboard");
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-neutral-900 border border-neutral-800 rounded-lg p-6 max-w-6xl w-full max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Compare Synthesis Runs</h3>
          <div className="flex gap-2">
            <button
              onClick={exportComparison}
              disabled={runs.some(r => r.isLoading || r.isError || !r.data)}
              className="text-sm px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Export Comparison
            </button>
            <button onClick={onClose} className="text-neutral-500 hover:text-neutral-300">
              ✕
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {runs.map((r, idx) => {
            const run = r.data;
            return (
              <div key={runIds[idx]} className="border border-neutral-800 rounded p-4">
                <h4 className="font-semibold text-neutral-200 mb-2">
                  {run?.title || `Run #${runIds[idx]}`}
                </h4>
                {r.isLoading ? (
                  <div className="text-sm text-neutral-500">Loading...</div>
                ) : run ? (
                  <div className="space-y-3 text-sm">
                    <div>
                      <span className="text-xs text-neutral-500">Summary:</span>
                      <p className="text-neutral-300 mt-1">{run.summary || "N/A"}</p>
                    </div>
                    <div>
                      <span className="text-xs text-neutral-500">Key Insights:</span>
                      <ul className="list-disc list-inside text-neutral-300 mt-1 space-y-1">
                        {Array.isArray(run.key_insights) && run.key_insights.length > 0 ? (
                          run.key_insights.map((insight: string, i: number) => (
                            <li key={i} className="text-xs">{insight}</li>
                          ))
                        ) : (
                          <li className="text-neutral-500">None</li>
                        )}
                      </ul>
                    </div>
                    <div>
                      <span className="text-xs text-neutral-500">Repositories:</span>
                      <div className="mt-1 space-y-1">
                        {(() => {
                          const diff = getRepoDiff(idx);
                          return (
                            <>
                              {diff.unique.length > 0 && (
                                <div>
                                  <div className="text-xs text-green-400">Unique to this run:</div>
                                  {diff.unique.map(id => (
                                    <div key={id} className="text-xs text-green-300 ml-2">+ {getRepoName(id)}</div>
                                  ))}
                                </div>
                              )}
                              {diff.common.length > 0 && (
                                <div>
                                  <div className="text-xs text-neutral-500">Common:</div>
                                  {diff.common.map(id => (
                                    <div key={id} className="text-xs text-neutral-400 ml-2">{getRepoName(id)}</div>
                                  ))}
                                </div>
                              )}
                              {diff.missing.length > 0 && (
                                <div>
                                  <div className="text-xs text-red-400">Missing from this run:</div>
                                  {diff.missing.map(id => (
                                    <div key={id} className="text-xs text-red-300 ml-2">- {getRepoName(id)}</div>
                                  ))}
                                </div>
                              )}
                            </>
                          );
                        })()}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-neutral-500">Not found</div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

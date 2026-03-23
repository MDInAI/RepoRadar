"use client";

import { useSynthesisRun } from "@/hooks/useSynthesis";
import { useQuery } from "@tanstack/react-query";
import { fetchRepositoryDetail } from "@/api/repositories";
import { fetchIdeaFamily } from "@/api/idea-families";
import { formatAppDateTime } from "@/lib/time";

interface SynthesisRunDetailDialogProps {
  runId: number;
  onClose: () => void;
}

export function SynthesisRunDetailDialog({ runId, onClose }: SynthesisRunDetailDialogProps) {
  const { data: run, isLoading } = useSynthesisRun(runId);

  // Fetch family details
  const familyQuery = useQuery({
    queryKey: ["idea-family", run?.idea_family_id],
    queryFn: () => fetchIdeaFamily(run!.idea_family_id!),
    enabled: !!run?.idea_family_id,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
  const family = familyQuery.data;

  // Fetch repository details for links
  const repoQueries = useQuery({
    queryKey: ["synthesis-run-repos", runId, run?.input_repository_ids],
    queryFn: async () => {
      if (!run?.input_repository_ids) return [];
      return Promise.all(
        run.input_repository_ids.map(id => fetchRepositoryDetail(id).catch(() => null))
      );
    },
    enabled: !!run?.input_repository_ids,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const copyToClipboard = () => {
    if (run?.output_text) {
      navigator.clipboard.writeText(run.output_text);
      alert("Copied to clipboard!");
    }
  };

  const getRepoNames = () => {
    if (!run || !repoQueries.data) return "None";
    return repoQueries.data.map(repo => repo?.full_name || "Unknown").join(", ");
  };

  const exportAsMarkdown = () => {
    if (!run || !family?.title || !repoQueries.data) return;
    const familyName = family.title.replace(/[^a-z0-9-]/gi, "_");
    const date = new Date(run.created_at).toISOString().split("T")[0];
    const repoNames = getRepoNames();
    const content = `# ${run.title || `Synthesis Run #${run.id}`}

**Created:** ${formatAppDateTime(run.created_at)}
${run.completed_at ? `**Completed:** ${formatAppDateTime(run.completed_at)}\n` : ""}
**Summary:** ${run.summary || "N/A"}

**Key Insights:**
${run.key_insights?.map((i: string) => `- ${i}`).join("\n") || "None"}

**Source Repositories:** ${repoNames}

**Full Output:**

${run.output_text || ""}`;
    const blob = new Blob([content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `synthesis-${familyName}-${date}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportAsJson = () => {
    if (!run || !family?.title || !repoQueries.data) return;
    const familyName = family.title.replace(/[^a-z0-9-]/gi, "_");
    const date = new Date(run.created_at).toISOString().split("T")[0];
    const repoNames = repoQueries.data.map(repo => repo?.full_name || "Unknown");
    const payload = {
      id: run.id,
      title: run.title,
      summary: run.summary,
      key_insights: run.key_insights,
      input_repository_ids: run.input_repository_ids,
      source_repositories: repoNames,
      output_text: run.output_text,
      status: run.status,
      created_at: run.created_at,
      completed_at: run.completed_at,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `synthesis-${familyName}-${date}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportAsText = () => {
    if (!run || !family?.title || !repoQueries.data) return;
    const familyName = family.title.replace(/[^a-z0-9-]/gi, "_");
    const date = new Date(run.created_at).toISOString().split("T")[0];
    const repoNames = getRepoNames();
    const content = `Synthesis Run #${run.id}

Title: ${run.title || "N/A"}
Created: ${formatAppDateTime(run.created_at)}
${run.completed_at ? `Completed: ${formatAppDateTime(run.completed_at)}\n` : ""}
Summary: ${run.summary || "N/A"}

Key Insights:
${run.key_insights?.map((i: string) => `- ${i}`).join("\n") || "None"}

Source Repositories: ${repoNames}

Full Output:

${run.output_text || ""}`;
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `synthesis-${familyName}-${date}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-neutral-900 border border-neutral-800 rounded-lg p-6 max-w-2xl w-full max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Synthesis Run #{runId}</h3>
          <div className="flex items-center gap-2">
            <button
              onClick={exportAsMarkdown}
              disabled={!run || familyQuery.isLoading || repoQueries.isLoading || !family?.title}
              className="text-xs px-2 py-1 bg-neutral-800 hover:bg-neutral-700 rounded disabled:opacity-50 disabled:cursor-not-allowed"
              title="Export as Markdown"
            >
              MD
            </button>
            <button
              onClick={exportAsJson}
              disabled={!run || familyQuery.isLoading || repoQueries.isLoading || !family?.title}
              className="text-xs px-2 py-1 bg-neutral-800 hover:bg-neutral-700 rounded disabled:opacity-50 disabled:cursor-not-allowed"
              title="Export as JSON"
            >
              JSON
            </button>
            <button
              onClick={exportAsText}
              disabled={!run || familyQuery.isLoading || repoQueries.isLoading || !family?.title}
              className="text-xs px-2 py-1 bg-neutral-800 hover:bg-neutral-700 rounded disabled:opacity-50 disabled:cursor-not-allowed"
              title="Export as Text"
            >
              TXT
            </button>
            <button onClick={onClose} className="text-neutral-500 hover:text-neutral-300">
              ✕
            </button>
          </div>
        </div>

        {isLoading ? (
          <div className="text-sm text-neutral-500">Loading...</div>
        ) : run ? (
          <div className="space-y-4">
            {run.title && (
              <div>
                <h2 className="text-xl font-bold text-neutral-100">{run.title}</h2>
              </div>
            )}

            <div>
              <span className="text-xs text-neutral-500">Status:</span>
              <span
                className={`ml-2 px-2 py-0.5 rounded text-xs ${
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

            {run.summary && (
              <div>
                <span className="text-xs text-neutral-500">Summary:</span>
                <div className="mt-1 text-sm text-neutral-300">{run.summary}</div>
              </div>
            )}

            {run.key_insights && Array.isArray(run.key_insights) && run.key_insights.length > 0 && (
              <div>
                <span className="text-xs text-neutral-500">Key Insights:</span>
                <ul className="mt-1 text-sm text-neutral-300 list-disc list-inside space-y-1">
                  {run.key_insights.map((insight: string, idx: number) => (
                    <li key={idx}>{insight}</li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <span className="text-xs text-neutral-500">Input Repositories:</span>
              <div className="mt-1 text-sm space-y-1">
                {repoQueries.data?.map((repo, idx) =>
                  repo ? (
                    <div key={repo.github_repository_id}>
                      <a
                        href={`/repositories/${repo.github_repository_id}`}
                        className="text-blue-400 hover:text-blue-300"
                      >
                        {repo.full_name}
                      </a>
                    </div>
                  ) : (
                    <div key={run?.input_repository_ids[idx]} className="text-neutral-500">
                      Repository #{run?.input_repository_ids[idx]}
                    </div>
                  )
                )}
              </div>
            </div>

            {run.output_text && (
              <details>
                <summary className="text-xs text-neutral-500 cursor-pointer hover:text-neutral-400">
                  Full Output Text
                </summary>
                <div className="mt-2">
                  <button
                    onClick={copyToClipboard}
                    className="text-xs text-blue-400 hover:text-blue-300 mb-2"
                  >
                    Copy to Clipboard
                  </button>
                  <div className="bg-neutral-950 border border-neutral-800 rounded p-3 text-sm whitespace-pre-wrap">
                    {run.output_text}
                  </div>
                </div>
              </details>
            )}

            {run.error_message && (
              <div>
                <span className="text-xs text-neutral-500">Error:</span>
                <div className="mt-1 text-sm text-red-400">{run.error_message}</div>
              </div>
            )}

            <div className="text-xs text-neutral-600 space-y-1">
              <div>Created: {formatAppDateTime(run.created_at)}</div>
              {run.started_at && <div>Started: {formatAppDateTime(run.started_at)}</div>}
              {run.completed_at && <div>Completed: {formatAppDateTime(run.completed_at)}</div>}
            </div>
          </div>
        ) : (
          <div className="text-sm text-neutral-500">Run not found</div>
        )}
      </div>
    </div>
  );
}

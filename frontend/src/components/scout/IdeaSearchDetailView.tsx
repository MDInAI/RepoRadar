"use client";

import { useState } from "react";
import {
  useIdeaSearch,
  useIdeaSearchDiscoveries,
  useUpdateIdeaSearch,
  usePauseIdeaSearch,
  useResumeIdeaSearch,
  useCancelIdeaSearch,
} from "@/hooks/useIdeaScout";
import { IdeaSearchProgressBar } from "./IdeaSearchProgressBar";

interface IdeaSearchDetailViewProps {
  searchId: number;
}

export function IdeaSearchDetailView({ searchId }: IdeaSearchDetailViewProps) {
  const { data: search, isLoading } = useIdeaSearch(searchId);
  const [page, setPage] = useState(0);
  const pageSize = 20;
  const { data: discoveries } = useIdeaSearchDiscoveries(searchId, {
    limit: pageSize,
    offset: page * pageSize,
  });
  const [editingQueries, setEditingQueries] = useState(false);
  const [queryDraft, setQueryDraft] = useState("");
  const updateMutation = useUpdateIdeaSearch();
  const pauseMutation = usePauseIdeaSearch();
  const resumeMutation = useResumeIdeaSearch();
  const cancelMutation = useCancelIdeaSearch();

  if (isLoading || !search) {
    return <div className="p-4 text-sm text-neutral-400">Loading...</div>;
  }

  const handleSaveQueries = () => {
    const queries = queryDraft
      .split("\n")
      .map((q) => q.trim())
      .filter(Boolean);
    if (queries.length > 0) {
      updateMutation.mutate(
        { searchId, data: { search_queries: queries } },
        { onSuccess: () => setEditingQueries(false) }
      );
    }
  };

  const startEditing = () => {
    setQueryDraft(search.search_queries.join("\n"));
    setEditingQueries(true);
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">{search.idea_text}</h2>
          <div className="flex items-center gap-2 mt-1 text-xs text-neutral-400">
            <span>ID: {search.id}</span>
            <span>&middot;</span>
            <span className="capitalize">{search.direction}</span>
            <span>&middot;</span>
            <span className="capitalize">{search.status}</span>
            <span>&middot;</span>
            <span>{search.total_repos_found} repos</span>
          </div>
        </div>
        <div className="flex gap-2 shrink-0">
          {search.status === "active" && (
            <button
              onClick={() => pauseMutation.mutate(searchId)}
              disabled={pauseMutation.isPending}
              className="px-3 py-1.5 text-sm bg-yellow-900/40 text-yellow-400 rounded-lg hover:bg-yellow-900/60 transition-colors"
            >
              Pause
            </button>
          )}
          {search.status === "paused" && (
            <button
              onClick={() => resumeMutation.mutate(searchId)}
              disabled={resumeMutation.isPending}
              className="px-3 py-1.5 text-sm bg-green-900/40 text-green-400 rounded-lg hover:bg-green-900/60 transition-colors"
            >
              Resume
            </button>
          )}
          {(search.status === "active" || search.status === "paused") && (
            <button
              onClick={() => {
                if (confirm("Cancel this search?")) cancelMutation.mutate(searchId);
              }}
              disabled={cancelMutation.isPending}
              className="px-3 py-1.5 text-sm bg-red-900/40 text-red-400 rounded-lg hover:bg-red-900/60 transition-colors"
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {/* Progress */}
      <div className="p-3 bg-neutral-800/50 rounded-lg border border-neutral-700">
        <h3 className="text-sm font-medium mb-2">Progress</h3>
        <IdeaSearchProgressBar progress={search.progress} direction={search.direction} />
        {search.progress.length > 0 && (
          <div className="mt-3 space-y-1">
            {search.progress.map((p) => (
              <div key={p.query_index} className="flex items-center gap-2 text-xs text-neutral-400">
                <span className="font-mono w-6 text-right">Q{p.query_index}</span>
                <span>{p.window_start_date}</span>
                <span>&rarr;</span>
                <span>{p.created_before_boundary}</span>
                <span className="ml-auto">
                  {p.exhausted ? (
                    <span className="text-green-400">Done</span>
                  ) : (
                    <span>p{p.next_page} &middot; {p.pages_processed_in_run} pages this run</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Search Queries */}
      <div className="p-3 bg-neutral-800/50 rounded-lg border border-neutral-700">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium">Search Queries</h3>
          {!editingQueries && (search.status === "active" || search.status === "paused") && (
            <button
              onClick={startEditing}
              className="text-xs text-indigo-400 hover:text-indigo-300"
            >
              Edit
            </button>
          )}
        </div>
        {editingQueries ? (
          <div className="space-y-2">
            <textarea
              value={queryDraft}
              onChange={(e) => setQueryDraft(e.target.value)}
              rows={Math.max(3, search.search_queries.length + 1)}
              className="w-full px-3 py-2 bg-neutral-900 border border-neutral-600 rounded-lg text-xs font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="One query per line"
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setEditingQueries(false)}
                className="px-3 py-1 text-xs bg-neutral-700 rounded hover:bg-neutral-600 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveQueries}
                disabled={updateMutation.isPending}
                className="px-3 py-1 text-xs bg-indigo-600 rounded hover:bg-indigo-500 transition-colors disabled:opacity-50"
              >
                {updateMutation.isPending ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-1">
            {search.search_queries.map((q, i) => (
              <div key={i} className="text-xs font-mono text-neutral-300 bg-neutral-900/50 px-2 py-1 rounded">
                {q}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Discovered Repos */}
      <div className="p-3 bg-neutral-800/50 rounded-lg border border-neutral-700">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium">
            Discovered Repositories ({search.discovery_count})
          </h3>
        </div>
        {discoveries && discoveries.length > 0 ? (
          <>
            <div className="space-y-1">
              {discoveries.map((repo) => (
                <div
                  key={repo.github_repository_id}
                  className="flex items-center justify-between text-sm py-1.5 px-2 rounded hover:bg-neutral-700/50"
                >
                  <div className="min-w-0 flex-1">
                    <a
                      href={`https://github.com/${repo.full_name}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-indigo-400 hover:text-indigo-300 hover:underline truncate block"
                    >
                      {repo.full_name}
                    </a>
                    {repo.description && (
                      <p className="text-xs text-neutral-500 truncate">{repo.description}</p>
                    )}
                  </div>
                  <span className="text-xs text-neutral-400 ml-2 shrink-0">
                    ★ {repo.stargazers_count.toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between mt-3 pt-2 border-t border-neutral-700">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="text-xs text-neutral-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
              >
                ← Previous
              </button>
              <span className="text-xs text-neutral-500">
                Page {page + 1}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={discoveries.length < pageSize}
                className="text-xs text-neutral-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Next →
              </button>
            </div>
          </>
        ) : (
          <p className="text-xs text-neutral-500">No repositories discovered yet.</p>
        )}
      </div>
    </div>
  );
}

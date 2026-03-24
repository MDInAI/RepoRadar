"use client";

import { useIdeaSearches, usePauseIdeaSearch, useResumeIdeaSearch, useCancelIdeaSearch } from "@/hooks/useIdeaScout";
import type { IdeaSearchResponse, IdeaSearchStatus, IdeaSearchDirection } from "@/api/idea-scout";

interface IdeaSearchListProps {
  statusFilter?: IdeaSearchStatus;
  directionFilter?: IdeaSearchDirection;
  selectedSearchId?: number | null;
  onSelectSearch: (searchId: number) => void;
}

const STATUS_BADGE: Record<IdeaSearchStatus, { bg: string; text: string }> = {
  active: { bg: "bg-green-900/40", text: "text-green-400" },
  paused: { bg: "bg-yellow-900/40", text: "text-yellow-400" },
  completed: { bg: "bg-blue-900/40", text: "text-blue-400" },
  cancelled: { bg: "bg-neutral-700", text: "text-neutral-400" },
};

const DIRECTION_BADGE: Record<IdeaSearchDirection, { bg: string; text: string; label: string }> = {
  backward: { bg: "bg-purple-900/40", text: "text-purple-400", label: "Historical" },
  forward: { bg: "bg-teal-900/40", text: "text-teal-400", label: "Forward" },
};

function StatusBadge({ status }: { status: IdeaSearchStatus }) {
  const s = STATUS_BADGE[status];
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${s.bg} ${s.text}`}>
      {status}
    </span>
  );
}

function DirectionBadge({ direction }: { direction: IdeaSearchDirection }) {
  const d = DIRECTION_BADGE[direction];
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${d.bg} ${d.text}`}>
      {d.label}
    </span>
  );
}

export function IdeaSearchList({
  statusFilter,
  directionFilter,
  selectedSearchId,
  onSelectSearch,
}: IdeaSearchListProps) {
  const { data: searches, isLoading } = useIdeaSearches({
    status: statusFilter,
    direction: directionFilter,
  });
  const pauseMutation = usePauseIdeaSearch();
  const resumeMutation = useResumeIdeaSearch();
  const cancelMutation = useCancelIdeaSearch();

  if (isLoading) {
    return <div className="text-sm text-neutral-400 p-4">Loading searches...</div>;
  }

  if (!searches?.length) {
    return (
      <div className="text-sm text-neutral-500 p-4 text-center">
        No searches yet. Create one above.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {searches.map((search: IdeaSearchResponse) => {
        const isSelected = search.id === selectedSearchId;
        return (
          <div
            key={search.id}
            onClick={() => onSelectSearch(search.id)}
            className={`p-3 rounded-lg border cursor-pointer transition-colors ${
              isSelected
                ? "border-indigo-500 bg-indigo-950/30"
                : "border-neutral-700 bg-neutral-800/50 hover:border-neutral-600"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{search.idea_text}</p>
                <div className="flex items-center gap-2 mt-1">
                  <StatusBadge status={search.status} />
                  <DirectionBadge direction={search.direction} />
                  <span className="text-xs text-neutral-500">
                    {search.total_repos_found} repos found
                  </span>
                </div>
                <p className="text-xs text-neutral-500 mt-1">
                  {search.search_queries.length} quer{search.search_queries.length === 1 ? "y" : "ies"}
                </p>
              </div>
              <div className="flex gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                {search.status === "active" && (
                  <button
                    onClick={() => pauseMutation.mutate(search.id)}
                    disabled={pauseMutation.isPending}
                    className="px-2 py-1 text-xs bg-yellow-900/40 text-yellow-400 rounded hover:bg-yellow-900/60 transition-colors"
                    title="Pause"
                  >
                    ⏸
                  </button>
                )}
                {search.status === "paused" && (
                  <button
                    onClick={() => resumeMutation.mutate(search.id)}
                    disabled={resumeMutation.isPending}
                    className="px-2 py-1 text-xs bg-green-900/40 text-green-400 rounded hover:bg-green-900/60 transition-colors"
                    title="Resume"
                  >
                    ▶
                  </button>
                )}
                {(search.status === "active" || search.status === "paused") && (
                  <button
                    onClick={() => {
                      if (confirm("Cancel this search?")) {
                        cancelMutation.mutate(search.id);
                      }
                    }}
                    disabled={cancelMutation.isPending}
                    className="px-2 py-1 text-xs bg-red-900/40 text-red-400 rounded hover:bg-red-900/60 transition-colors"
                    title="Cancel"
                  >
                    ✕
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

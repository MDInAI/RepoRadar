"use client";

import {
  useCancelIdeaSearch,
  useIdeaSearches,
  usePauseIdeaSearch,
  useResumeIdeaSearch,
  useSetAnalystEnabled,
} from "@/hooks/useIdeaScout";
import type { IdeaSearchDirection, IdeaSearchResponse, IdeaSearchStatus } from "@/api/idea-scout";

interface IdeaSearchListProps {
  searchTerm?: string;
  statusFilter?: IdeaSearchStatus;
  directionFilter?: IdeaSearchDirection;
  selectedSearchId?: number | null;
  onSelectSearch: (searchId: number) => void;
}

const STATUS_ORDER: IdeaSearchStatus[] = ["active", "paused", "completed", "cancelled"];

function dotClass(status: IdeaSearchStatus): string {
  return `scout-scard-dot scout-scard-dot-${status}`;
}

function dirLabel(direction: IdeaSearchDirection): string {
  return direction === "backward" ? "Historical" : "Forward";
}

function timeAgo(value: string): string {
  const ms = Date.now() - new Date(value).getTime();
  const min = Math.floor(ms / 60000);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}

function matchesSearchTerm(search: IdeaSearchResponse, term: string): boolean {
  const normalized = term.trim().toLowerCase();
  if (!normalized) return true;
  return (
    search.idea_text.toLowerCase().includes(normalized) ||
    search.search_queries.some((q) => q.toLowerCase().includes(normalized))
  );
}

function SearchCard({
  search,
  isSelected,
  onSelect,
}: {
  search: IdeaSearchResponse;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const pauseMutation = usePauseIdeaSearch();
  const resumeMutation = useResumeIdeaSearch();
  const cancelMutation = useCancelIdeaSearch();
  const analystMutation = useSetAnalystEnabled();

  const analystPending = analystMutation.isPending;

  return (
    <div
      className={`scout-scard ${isSelected ? "scout-scard-selected" : ""}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onSelect()}
    >
      <div className="scout-scard-toprow">
        <span className={dotClass(search.status)} />
        <span className="scout-scard-idea">{search.idea_text}</span>
      </div>
      <div className="scout-scard-meta">
        <span>{search.search_queries.length} queries</span>
        <span>{search.total_repos_found.toLocaleString()} repos</span>
        <span>{dirLabel(search.direction)}</span>
        <span>{timeAgo(search.updated_at)}</span>
      </div>

      {/* Analyst toggle — always visible so you can activate it from any state */}
      <div className="scout-scard-analyst" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className={`scout-scard-analyst-btn ${search.analyst_enabled ? "scout-scard-analyst-btn-on" : "scout-scard-analyst-btn-off"}`}
          disabled={analystPending}
          title={search.analyst_enabled ? "Analyst is processing this search — click to stop" : "Enable Analyst for this search to score and tag all discoveries"}
          onClick={() =>
            analystMutation.mutate({ searchId: search.id, enabled: !search.analyst_enabled })
          }
        >
          <span className="scout-scard-analyst-dot" />
          {search.analyst_enabled ? "Analyst On" : "Analyst Off"}
        </button>
      </div>

      {(search.status === "active" || search.status === "paused") && (
        <div className="scout-scard-actions" onClick={(e) => e.stopPropagation()}>
          {search.status === "active" && (
            <button
              type="button"
              className="scout-scard-action scout-scard-action-pause"
              disabled={pauseMutation.isPending}
              onClick={() => pauseMutation.mutate(search.id)}
            >
              Pause
            </button>
          )}
          {search.status === "paused" && (
            <button
              type="button"
              className="scout-scard-action scout-scard-action-resume"
              disabled={resumeMutation.isPending}
              onClick={() => resumeMutation.mutate(search.id)}
            >
              Resume
            </button>
          )}
          <button
            type="button"
            className="scout-scard-action scout-scard-action-danger"
            disabled={cancelMutation.isPending}
            onClick={() => {
              if (confirm(`Stop "${search.idea_text}"?`)) cancelMutation.mutate(search.id);
            }}
          >
            Stop
          </button>
        </div>
      )}
    </div>
  );
}

export function IdeaSearchList({
  searchTerm = "",
  statusFilter,
  directionFilter,
  selectedSearchId,
  onSelectSearch,
}: IdeaSearchListProps) {
  const { data: searches, isLoading, isError, error, isFetching } = useIdeaSearches({
    status: statusFilter,
    direction: directionFilter,
  });

  if (isLoading) {
    return <div className="scout-list-loading">{isFetching ? "Loading…" : "No data"}</div>;
  }

  if (isError) {
    return (
      <div className="scout-list-error">
        {error instanceof Error ? error.message : "Failed to load searches."}
      </div>
    );
  }

  const filtered = (searches ?? []).filter((s) => matchesSearchTerm(s, searchTerm));

  if (filtered.length === 0) {
    return <div className="scout-list-empty">No searches match the current filters.</div>;
  }

  const sections = STATUS_ORDER.map((status) => ({
    status,
    items: filtered.filter((s) => s.status === status),
  })).filter((s) => s.items.length > 0);

  return (
    <>
      {sections.map(({ status, items }) => (
        <div key={status}>
          <div className="scout-list-section-label">{status} · {items.length}</div>
          {items.map((search) => (
            <SearchCard
              key={search.id}
              search={search}
              isSelected={search.id === selectedSearchId}
              onSelect={() => onSelectSearch(search.id)}
            />
          ))}
        </div>
      ))}
    </>
  );
}

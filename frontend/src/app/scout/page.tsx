"use client";

import { Suspense, useMemo, useState } from "react";
import type { IdeaSearchDirection, IdeaSearchStatus } from "@/api/idea-scout";
import { IdeaSearchForm } from "@/components/scout/IdeaSearchForm";
import { IdeaSearchList } from "@/components/scout/IdeaSearchList";
import { IdeaSearchDetailView } from "@/components/scout/IdeaSearchDetailView";
import { ScoutWorkerStatusBadge } from "@/components/scout/ScoutWorkerMonitor";
import { useIdeaSearches } from "@/hooks/useIdeaScout";

function ScoutPageContent() {
  const [selectedSearchId, setSelectedSearchId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<IdeaSearchStatus | undefined>(undefined);
  const [directionFilter, setDirectionFilter] = useState<IdeaSearchDirection | undefined>(undefined);
  const [searchTerm, setSearchTerm] = useState("");
  const [showNewForm, setShowNewForm] = useState(false);
  const { data: allSearches = [] } = useIdeaSearches();

  const preferredSearchId = useMemo(() => {
    if (allSearches.length === 0) return null;
    return (
      allSearches.find((s) => s.status === "active")?.id ??
      allSearches.find((s) => s.status === "paused")?.id ??
      allSearches[0]?.id ??
      null
    );
  }, [allSearches]);

  const effectiveSelectedSearchId =
    selectedSearchId !== null && allSearches.some((s) => s.id === selectedSearchId)
      ? selectedSearchId
      : preferredSearchId;

  const activeCount = allSearches.filter((s) => s.status === "active").length;
  const pausedCount = allSearches.filter((s) => s.status === "paused").length;
  const totalReposFound = allSearches.reduce((t, s) => t + s.total_repos_found, 0);

  const hasFilter = statusFilter !== undefined || directionFilter !== undefined || searchTerm !== "";

  return (
    <div className="scout-workspace">
      {/* LEFT SIDEBAR */}
      <aside className="scout-sidebar">
        <div className="scout-sidebar-header">
          <div className="scout-sidebar-toprow">
            <span className="scout-sidebar-title">Scout</span>
            <div className="scout-sidebar-stats">
              <span className={`scout-sidebar-stat ${activeCount > 0 ? "scout-sidebar-stat-active" : ""}`}>
                {activeCount} active
              </span>
              <span className="scout-sidebar-stat">{pausedCount} paused</span>
              <span className="scout-sidebar-stat">{totalReposFound.toLocaleString()} repos</span>
            </div>
          </div>

          <button
            type="button"
            className={`scout-new-btn ${showNewForm ? "scout-new-btn-cancel" : ""}`}
            onClick={() => setShowNewForm((v) => !v)}
          >
            {showNewForm ? "Cancel" : "+ New search"}
          </button>

          <input
            className="scout-filter-input"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Filter searches..."
          />

          <div className="scout-filter-chips">
            {(["active", "paused", "completed", "cancelled"] as IdeaSearchStatus[]).map((s) => (
              <button
                key={s}
                type="button"
                className={`scout-filter-chip ${statusFilter === s ? "scout-filter-chip-on" : ""}`}
                onClick={() => setStatusFilter((c) => (c === s ? undefined : s))}
              >
                {s}
              </button>
            ))}
          </div>

          <div className="scout-filter-chips">
            <button
              type="button"
              className={`scout-filter-chip ${directionFilter === "backward" ? "scout-filter-chip-on" : ""}`}
              onClick={() => setDirectionFilter((c) => (c === "backward" ? undefined : "backward"))}
            >
              Historical
            </button>
            <button
              type="button"
              className={`scout-filter-chip ${directionFilter === "forward" ? "scout-filter-chip-on" : ""}`}
              onClick={() => setDirectionFilter((c) => (c === "forward" ? undefined : "forward"))}
            >
              Forward
            </button>
            {hasFilter && (
              <button
                type="button"
                className="scout-filter-chip scout-filter-chip-clear"
                onClick={() => { setStatusFilter(undefined); setDirectionFilter(undefined); setSearchTerm(""); }}
              >
                Clear
              </button>
            )}
          </div>
        </div>

        <div className="scout-sidebar-worker">
          <ScoutWorkerStatusBadge />
        </div>

        <div className="scout-sidebar-list">
          <IdeaSearchList
            searchTerm={searchTerm}
            statusFilter={statusFilter}
            directionFilter={directionFilter}
            selectedSearchId={effectiveSelectedSearchId}
            onSelectSearch={(id) => { setSelectedSearchId(id); setShowNewForm(false); }}
          />
        </div>
      </aside>

      {/* RIGHT CONTENT */}
      <div className="scout-content">
        {showNewForm ? (
          <div className="scout-content-inner">
            <IdeaSearchForm onCreated={(id) => { setSelectedSearchId(id); setShowNewForm(false); }} />
          </div>
        ) : effectiveSelectedSearchId ? (
          <div className="scout-content-inner">
            <IdeaSearchDetailView searchId={effectiveSelectedSearchId} />
          </div>
        ) : (
          <div className="scout-content-empty">
            <div className="scout-content-empty-icon">◎</div>
            <p className="scout-content-empty-title">No search selected</p>
            <p className="scout-content-empty-sub">Create a new search or select one from the sidebar.</p>
            <button type="button" className="scout-primary-btn" onClick={() => setShowNewForm(true)}>
              + New search
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ScoutPage() {
  return (
    <Suspense fallback={<div className="scout-workspace"><div className="scout-loading">Loading Scout…</div></div>}>
      <ScoutPageContent />
    </Suspense>
  );
}

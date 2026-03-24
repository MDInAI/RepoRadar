"use client";

import { useState, Suspense } from "react";
import { IdeaSearchForm } from "@/components/scout/IdeaSearchForm";
import { IdeaSearchList } from "@/components/scout/IdeaSearchList";
import { IdeaSearchDetailView } from "@/components/scout/IdeaSearchDetailView";
import type { IdeaSearchStatus, IdeaSearchDirection } from "@/api/idea-scout";

function ScoutPageContent() {
  const [selectedSearchId, setSelectedSearchId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<IdeaSearchStatus | undefined>(undefined);
  const [directionFilter, setDirectionFilter] = useState<IdeaSearchDirection | undefined>(undefined);

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Scout</span>
        <span className="topbar-breadcrumb">idea-driven discovery</span>
      </div>

      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Left panel: form + list */}
        <div
          style={{ width: "380px", borderRight: "1px solid var(--border)" }}
          className="flex flex-col overflow-hidden"
        >
          <div className="p-3 border-b border-neutral-700">
            <IdeaSearchForm
              onCreated={(id) => setSelectedSearchId(id)}
            />
          </div>

          {/* Filters */}
          <div className="flex gap-2 p-3 border-b border-neutral-700">
            <select
              value={statusFilter ?? ""}
              onChange={(e) =>
                setStatusFilter((e.target.value || undefined) as IdeaSearchStatus | undefined)
              }
              className="flex-1 px-2 py-1 text-xs bg-neutral-800 border border-neutral-700 rounded"
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
            </select>
            <select
              value={directionFilter ?? ""}
              onChange={(e) =>
                setDirectionFilter((e.target.value || undefined) as IdeaSearchDirection | undefined)
              }
              className="flex-1 px-2 py-1 text-xs bg-neutral-800 border border-neutral-700 rounded"
            >
              <option value="">All directions</option>
              <option value="backward">Backward</option>
              <option value="forward">Forward</option>
            </select>
          </div>

          <div className="flex-1 overflow-y-auto p-2">
            <IdeaSearchList
              statusFilter={statusFilter}
              directionFilter={directionFilter}
              selectedSearchId={selectedSearchId}
              onSelectSearch={setSelectedSearchId}
            />
          </div>
        </div>

        {/* Right panel: detail */}
        <div className="flex-1 overflow-y-auto p-4">
          {selectedSearchId ? (
            <IdeaSearchDetailView searchId={selectedSearchId} />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-neutral-500">
              <p className="text-lg font-medium mb-1">No search selected</p>
              <p className="text-sm">Create a search or select one from the list</p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export default function ScoutPage() {
  return (
    <Suspense
      fallback={<div className="flex h-screen items-center justify-center">Loading...</div>}
    >
      <ScoutPageContent />
    </Suspense>
  );
}

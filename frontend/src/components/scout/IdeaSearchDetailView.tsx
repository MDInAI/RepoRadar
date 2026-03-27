"use client";

import Link from "next/link";
import { useState } from "react";
import {
  useCancelIdeaSearch,
  useIdeaSearch,
  useIdeaSearchDiscoveries,
  usePauseIdeaSearch,
  useResumeIdeaSearch,
  useUpdateIdeaSearch,
} from "@/hooks/useIdeaScout";
import { IdeaSearchProgressBar } from "./IdeaSearchProgressBar";
import { ScoutWorkerMonitorPanel } from "./ScoutWorkerMonitor";

interface IdeaSearchDetailViewProps {
  searchId: number;
}

function fmtDate(value: string | null): string {
  if (!value) return "\u2014";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(d);
}

function errMsg(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function statusBadgeClass(status: "active" | "paused" | "completed" | "cancelled"): string {
  return `scout-badge scout-badge-${status}`;
}

// -- Overall progress helpers ------------------------------------------------

const SCAN_ORIGIN = new Date("2008-01-01").getTime();

function overallPct(windowStart: string): number {
  const today = Date.now();
  const cur = new Date(windowStart).getTime();
  const totalSpan = today - SCAN_ORIGIN;
  if (totalSpan <= 0) return 100;
  const scannedSpan = today - cur;
  return Math.min(100, Math.max(0, Math.round((scannedSpan / totalSpan) * 100)));
}

function fmtMonth(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, { month: "short", year: "numeric" }).format(d);
}

function monthsBetween(a: string, b: string): number {
  const da = new Date(a);
  const db = new Date(b);
  return Math.max(0, Math.round((db.getTime() - da.getTime()) / (30.44 * 24 * 60 * 60 * 1000)));
}

function timeRangeLabel(windowStart: string, boundary: string): string {
  return `${fmtMonth(windowStart)} \u2192 ${fmtMonth(boundary)}`;
}

function remainingLabel(windowStart: string): string {
  const months = monthsBetween("2008-01-01", windowStart);
  if (months <= 0) return "done";
  if (months < 12) return `~${months} months remaining`;
  const y = Math.floor(months / 12);
  const m = months % 12;
  return m === 0 ? `~${y} years remaining` : `~${y} yr ${m} mo remaining`;
}

// -- Component ---------------------------------------------------------------

export function IdeaSearchDetailView({ searchId }: IdeaSearchDetailViewProps) {
  return <DetailPanel key={searchId} searchId={searchId} />;
}

function DetailPanel({ searchId }: IdeaSearchDetailViewProps) {
  const { data: search, isLoading, isError, error } = useIdeaSearch(searchId);
  const [page, setPage] = useState(0);
  const pageSize = 20;
  const { data: discoveries, isError: discErr, error: discErrVal } = useIdeaSearchDiscoveries(searchId, {
    limit: pageSize,
    offset: page * pageSize,
  });
  const [editingQueries, setEditingQueries] = useState(false);
  const [queryDraft, setQueryDraft] = useState("");
  const updateMutation = useUpdateIdeaSearch();
  const pauseMutation = usePauseIdeaSearch();
  const resumeMutation = useResumeIdeaSearch();
  const cancelMutation = useCancelIdeaSearch();

  if (isLoading) return <div className="scout-loading">Loading\u2026</div>;
  if (isError || !search) return <div className="scout-detail-error">{errMsg(error, "Unable to load search.")}</div>;

  const completedQueries = search.progress.filter((p) => p.exhausted).length;
  const totalQueries = search.progress.length || search.search_queries.length;
  const hasErrors = search.progress.some((p) => p.consecutive_errors > 0);
  const pageStart = search.discovery_count === 0 ? 0 : page * pageSize + 1;
  const pageEnd = search.discovery_count === 0 ? 0 : Math.min(search.discovery_count, page * pageSize + (discoveries?.length ?? 0));

  const handleSaveQueries = () => {
    const queries = queryDraft.split("\n").map((q) => q.trim()).filter(Boolean);
    if (!queries.length) return;
    updateMutation.mutate({ searchId, data: { search_queries: queries } }, { onSuccess: () => setEditingQueries(false) });
  };

  const startEditing = () => {
    setQueryDraft(search.search_queries.join("\n"));
    setEditingQueries(true);
  };

  const canControl = search.status === "active" || search.status === "paused";

  return (
    <div>
      {/* TOP BAR */}
      <div className="scout-detail-topbar">
        <div className="scout-detail-left">
          <div className="scout-detail-badges">
            <span className={statusBadgeClass(search.status)}>{search.status}</span>
            <span className="scout-badge scout-badge-meta">{search.direction === "backward" ? "Historical" : "Forward"}</span>
            <span className="scout-badge scout-badge-meta">#{search.id}</span>
            {hasErrors && <span className="scout-badge scout-badge-error">has errors</span>}
          </div>
          <div className="scout-detail-idea">{search.idea_text}</div>
          <div className="scout-detail-actions">
            <Link href={`/repositories?source=idea_scout&ideaSearchId=${search.id}`} className="scout-action-btn scout-action-btn-catalog">
              View in catalog
            </Link>
            {search.status === "active" && (
              <button type="button" className="scout-action-btn scout-action-btn-pause" disabled={pauseMutation.isPending} onClick={() => pauseMutation.mutate(searchId)}>
                Pause
              </button>
            )}
            {search.status === "paused" && (
              <button type="button" className="scout-action-btn scout-action-btn-resume" disabled={resumeMutation.isPending} onClick={() => resumeMutation.mutate(searchId)}>
                Resume
              </button>
            )}
            {canControl && (
              <button type="button" className="scout-action-btn scout-action-btn-danger" disabled={cancelMutation.isPending} onClick={() => { if (confirm(`Stop "${search.idea_text}"?`)) cancelMutation.mutate(searchId); }}>
                Stop
              </button>
            )}
            {!editingQueries && canControl && (
              <button type="button" className="scout-action-btn" onClick={startEditing}>Edit queries</button>
            )}
          </div>
          {(pauseMutation.error || resumeMutation.error || cancelMutation.error) && (
            <div className="scout-detail-error" style={{ marginTop: 10 }}>
              {errMsg(pauseMutation.error || resumeMutation.error || cancelMutation.error, "Action failed.")}
            </div>
          )}
        </div>

        <div className="scout-detail-right">
          <div className="scout-meta-table">
            <div className="scout-meta-row"><span className="scout-meta-key">Created</span><span className="scout-meta-val">{fmtDate(search.created_at)}</span></div>
            <div className="scout-meta-row"><span className="scout-meta-key">Updated</span><span className="scout-meta-val">{fmtDate(search.updated_at)}</span></div>
            <div className="scout-meta-row"><span className="scout-meta-key">Discoveries</span><span className="scout-meta-val">{search.discovery_count.toLocaleString()} repos</span></div>
            <div className="scout-meta-row"><span className="scout-meta-key">Queries done</span><span className="scout-meta-val">{completedQueries}/{totalQueries}</span></div>
          </div>
        </div>
      </div>

      {/* OVERALL PROGRESS BAR */}
      <IdeaSearchProgressBar progress={search.progress} direction={search.direction} totalQueries={totalQueries} />

      {/* PER-QUERY SCAN STATUS */}
      <div className="scout-detail-section" style={{ marginTop: 16 }}>
        <div className="scout-section-head">
          <span className="scout-section-title">Scan progress by query</span>
        </div>
        <QueryScanTable progress={search.progress} queries={search.search_queries} direction={search.direction} />
      </div>

      {/* QUERY PACK */}
      <div className="scout-detail-section">
        <div className="scout-section-head">
          <span className="scout-section-title">Query pack</span>
          {!editingQueries && canControl && (
            <button type="button" className="scout-action-btn" onClick={startEditing}>Edit</button>
          )}
        </div>
        {editingQueries ? (
          <div>
            <textarea
              value={queryDraft}
              onChange={(e) => setQueryDraft(e.target.value)}
              rows={Math.max(8, search.search_queries.length + 2)}
              className="scout-query-editor"
              placeholder="One query per line"
            />
            {updateMutation.error && (
              <div className="scout-detail-error" style={{ marginTop: 8 }}>
                {errMsg(updateMutation.error, "Failed to save.")}
              </div>
            )}
            <div className="scout-editor-actions">
              <button type="button" className="scout-action-btn" onClick={() => setEditingQueries(false)}>Cancel</button>
              <button type="button" className="scout-action-btn scout-action-btn-resume" disabled={updateMutation.isPending} onClick={handleSaveQueries}>
                {updateMutation.isPending ? "Saving\u2026" : "Save"}
              </button>
            </div>
          </div>
        ) : (
          <div className="scout-query-cards">
            {search.search_queries.map((q, i) => {
              const prog = search.progress.find((p) => p.query_index === i);
              return (
                <div key={`${q}-${i}`} className="scout-qcard">
                  <div className="scout-qcard-header">
                    <span className="scout-qcard-num">Q{i + 1}</span>
                    {prog?.exhausted && <span className="scout-badge scout-badge-completed">done</span>}
                    {prog && prog.consecutive_errors > 0 && <span className="scout-badge scout-badge-error">error</span>}
                  </div>
                  <div className="scout-qcard-text">{q}</div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* WORKER MONITOR */}
      <ScoutWorkerMonitorPanel />

      {/* DISCOVERIES */}
      <div className="scout-discoveries-section">
        <div className="scout-discoveries-head">
          <span className="scout-section-title">Discoveries</span>
          <span className="scout-discoveries-count">
            {pageStart === 0 ? "0" : `${pageStart}\u2013${pageEnd}`} of {search.discovery_count.toLocaleString()}
          </span>
        </div>

        {discErr ? (
          <div className="scout-detail-error">{errMsg(discErrVal, "Unable to load discoveries.")}</div>
        ) : discoveries && discoveries.length > 0 ? (
          <>
            <div className="scout-discovery-grid">
              {discoveries.map((repo) => (
                <div key={repo.github_repository_id} className="scout-dcard">
                  <div className="scout-dcard-top">
                    <a href={`https://github.com/${repo.full_name}`} target="_blank" rel="noopener noreferrer" className="scout-dcard-name">
                      {repo.full_name}
                    </a>
                    <span className="scout-dcard-stars">{repo.stargazers_count.toLocaleString()}</span>
                  </div>
                  <p className="scout-dcard-desc">{repo.description || "No description."}</p>
                  <div className="scout-dcard-footer">
                    <span className="scout-dcard-date">{fmtDate(repo.discovered_at)}</span>
                    <a href={`https://github.com/${repo.full_name}`} target="_blank" rel="noopener noreferrer" className="scout-action-btn">
                      GitHub
                    </a>
                  </div>
                </div>
              ))}
            </div>
            <div className="scout-pagination">
              <button type="button" className="scout-action-btn" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
                Prev
              </button>
              <span className="scout-page-info">Page {page + 1}</span>
              <button type="button" className="scout-action-btn" disabled={(discoveries?.length ?? 0) < pageSize} onClick={() => setPage((p) => p + 1)}>
                Next
              </button>
            </div>
          </>
        ) : (
          <div className="scout-discoveries-empty">No repositories discovered yet.</div>
        )}
      </div>
    </div>
  );
}

// -- Per-query scan table ----------------------------------------------------

interface QueryScanTableProps {
  progress: import("@/api/idea-scout").IdeaSearchProgressSummary[];
  queries: string[];
  direction: "backward" | "forward";
}

function QueryScanTable({ progress, queries, direction }: QueryScanTableProps) {
  if (!progress.length) {
    return <div className="scout-progress-empty-text">Waiting for first scan cycle\u2026</div>;
  }

  if (direction === "forward") {
    return (
      <div className="scout-scan-progress">
        {progress.map((p) => (
          <div key={p.query_index} className="scout-scan-row">
            <span className="scout-scan-qnum">Q{p.query_index + 1}</span>
            <span className="scout-scan-detail">Watching for new repos &middot; last checked {fmtDate(p.last_checkpointed_at)}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="scout-scan-progress">
      {progress.map((p) => {
        const pct = p.exhausted ? 100 : overallPct(p.window_start_date);
        const hasError = p.consecutive_errors > 0;
        return (
          <div key={p.query_index} className={`scout-scan-row ${hasError ? "scout-scan-row-error" : ""}`}>
            <div className="scout-scan-top">
              <span className="scout-scan-qnum">Q{p.query_index + 1}</span>
              {p.exhausted ? (
                <span className="scout-scan-now scout-scan-done">Fully scanned (2008 \u2013 today)</span>
              ) : (
                <span className="scout-scan-now">
                  Currently scanning: <strong>{fmtMonth(p.window_start_date)}</strong>
                </span>
              )}
              <span className="scout-scan-pct">{pct}%</span>
            </div>

            {/* Overall progress bar */}
            <div className="scout-scan-bar-row">
              <span className="scout-scan-stat scout-scan-stat-back">2008</span>
              <div className="scout-scan-bar">
                <div
                  className={`scout-scan-bar-fill ${hasError ? "scout-scan-bar-fill-error" : ""}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="scout-scan-stat scout-scan-stat-left">today</span>
            </div>

            {/* Status line */}
            <div className="scout-scan-sub">
              {p.exhausted ? (
                "Completed"
              ) : (
                <>
                  Scanning {timeRangeLabel(p.window_start_date, p.created_before_boundary)} &middot; {remainingLabel(p.window_start_date)}
                </>
              )}
            </div>

            {/* Error banner */}
            {hasError && p.last_error && (
              <div className="scout-scan-error">
                Error ({p.consecutive_errors}x): {p.last_error}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

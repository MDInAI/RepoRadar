"use client";

import { useState } from "react";
import type { AgentRunEvent, AgentStatusEntry, SystemEventPayload } from "@/api/agents";
import {
  useIdeaScoutWorkerStatus,
  useIdeaScoutWorkerRuns,
  useIdeaScoutWorkerEvents,
} from "@/hooks/useAgentMonitor";

function timeAgo(value: string | null): string {
  if (!value) return "never";
  const diff = Date.now() - new Date(value).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function fmtDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function fmtTime(value: string): string {
  const d = new Date(value);
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(d);
}

function runStatusClass(status: AgentRunEvent["status"]): string {
  if (status === "running") return "monitor-run-status monitor-run-status-running";
  if (status === "completed") return "monitor-run-status monitor-run-status-ok";
  if (status === "failed") return "monitor-run-status monitor-run-status-fail";
  if (status === "skipped" || status === "skipped_paused") return "monitor-run-status monitor-run-status-skip";
  return "monitor-run-status";
}

function runStatusLabel(status: AgentRunEvent["status"]): string {
  if (status === "running") return "running";
  if (status === "completed") return "ok";
  if (status === "failed") return "failed";
  if (status === "skipped") return "skipped";
  if (status === "skipped_paused") return "paused";
  return status;
}

function eventSeverityClass(severity: SystemEventPayload["severity"]): string {
  if (severity === "error" || severity === "critical") return "monitor-ev-sev monitor-ev-sev-error";
  if (severity === "warning") return "monitor-ev-sev monitor-ev-sev-warn";
  return "monitor-ev-sev monitor-ev-sev-info";
}

interface WorkerHeaderProps {
  entry: AgentStatusEntry | null;
  isLoading: boolean;
}

function WorkerHeader({ entry, isLoading }: WorkerHeaderProps) {
  if (isLoading) return <div className="monitor-status-bar monitor-status-loading">Loading worker status…</div>;

  const run = entry?.latest_run;
  const isRunning = run?.status === "running";
  const isFailed = run?.status === "failed";

  let dotClass = "monitor-dot monitor-dot-idle";
  let label = "Worker idle";
  if (isRunning) { dotClass = "monitor-dot monitor-dot-running"; label = "Worker running now"; }
  else if (isFailed) { dotClass = "monitor-dot monitor-dot-error"; label = "Last run failed"; }

  const lastRan = run ? timeAgo(run.started_at) : null;
  const repos = run?.items_processed ?? null;

  return (
    <div className="monitor-status-bar">
      <span className={dotClass} />
      <span className="monitor-status-label">{label}</span>
      {lastRan && !isRunning && (
        <span className="monitor-status-meta">· {lastRan}{repos !== null ? ` · ${repos} repos` : ""}</span>
      )}
      {isRunning && run?.started_at && (
        <span className="monitor-status-meta">· started {timeAgo(run.started_at)}</span>
      )}
    </div>
  );
}

/** Compact sidebar badge — always visible */
export function ScoutWorkerStatusBadge() {
  const { data: entry, isLoading } = useIdeaScoutWorkerStatus();
  return <WorkerHeader entry={entry ?? null} isLoading={isLoading} />;
}

/** Full monitoring panel shown in detail view */
export function ScoutWorkerMonitorPanel() {
  const [open, setOpen] = useState(false);
  const { data: entry, isLoading: statusLoading } = useIdeaScoutWorkerStatus();
  const { data: runs, isLoading: runsLoading } = useIdeaScoutWorkerRuns(8, open);
  const { data: events, isLoading: eventsLoading } = useIdeaScoutWorkerEvents(12, open);

  const run = entry?.latest_run;
  const isRunning = run?.status === "running";
  const isFailed = run?.status === "failed";
  const hasStuckRisk =
    !isRunning && run?.started_at
      ? Date.now() - new Date(run.started_at).getTime() > 15 * 60 * 1000
      : false;

  return (
    <div className="monitor-panel">
      <button
        type="button"
        className="monitor-toggle"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="monitor-toggle-left">
          <span
            className={
              isRunning
                ? "monitor-dot monitor-dot-running"
                : isFailed
                ? "monitor-dot monitor-dot-error"
                : "monitor-dot monitor-dot-idle"
            }
          />
          <span className="monitor-toggle-title">Worker Activity</span>
          {!statusLoading && run && (
            <span className="monitor-toggle-hint">
              {isRunning
                ? `Running · started ${timeAgo(run.started_at)}`
                : `Last run ${timeAgo(run.started_at)}`}
              {!isRunning && run.items_processed !== null
                ? ` · ${run.items_processed} repos`
                : ""}
            </span>
          )}
          {hasStuckRisk && (
            <span className="monitor-warn-chip">long gap — check logs</span>
          )}
        </span>
        <span className="monitor-toggle-chevron">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="monitor-body">
          {/* Current run summary */}
          <div className="monitor-section">
            <div className="monitor-section-title">Current status</div>
            {statusLoading ? (
              <div className="monitor-loading">Loading…</div>
            ) : run ? (
              <div className="monitor-current-run">
                <div className="monitor-current-row">
                  <span className={runStatusClass(run.status)}>{runStatusLabel(run.status)}</span>
                  <span className="monitor-current-time">
                    Started {fmtTime(run.started_at)}
                    {run.completed_at ? ` · finished ${fmtTime(run.completed_at)}` : ""}
                  </span>
                  {run.duration_seconds !== null && (
                    <span className="monitor-current-dur">{fmtDuration(run.duration_seconds)}</span>
                  )}
                </div>
                {run.items_processed !== null && (
                  <div className="monitor-current-counts">
                    {run.items_processed} repos processed
                    {run.items_succeeded !== null && run.items_succeeded !== run.items_processed
                      ? ` · ${run.items_succeeded} succeeded`
                      : ""}
                    {run.items_failed !== null && run.items_failed > 0
                      ? ` · ${run.items_failed} failed`
                      : ""}
                  </div>
                )}
                {run.error_summary && (
                  <div className="monitor-error-line">{run.error_summary}</div>
                )}
                {entry?.runtime_progress && (
                  <div className="monitor-runtime-progress">
                    <span className="monitor-rt-label">{entry.runtime_progress.status_label}</span>
                    {entry.runtime_progress.current_activity && (
                      <span className="monitor-rt-activity"> · {entry.runtime_progress.current_activity}</span>
                    )}
                  </div>
                )}
                {hasStuckRisk && (
                  <div className="monitor-stuck-hint">
                    The worker has not run in over 15 minutes. This may be normal if the interval is configured
                    to be long, or the service may need restarting.
                  </div>
                )}
              </div>
            ) : (
              <div className="monitor-empty">No runs recorded yet.</div>
            )}
          </div>

          {/* Recent runs */}
          <div className="monitor-section">
            <div className="monitor-section-title">Recent runs</div>
            {runsLoading ? (
              <div className="monitor-loading">Loading…</div>
            ) : runs && runs.length > 0 ? (
              <div className="monitor-run-list">
                {runs.map((r) => (
                  <div key={r.id} className="monitor-run-row">
                    <span className={runStatusClass(r.status)}>{runStatusLabel(r.status)}</span>
                    <span className="monitor-run-time">{timeAgo(r.started_at)}</span>
                    <span className="monitor-run-dur">{fmtDuration(r.duration_seconds)}</span>
                    <span className="monitor-run-repos">
                      {r.items_processed !== null ? `${r.items_processed} repos` : "—"}
                    </span>
                    {r.error_summary && (
                      <span className="monitor-run-err" title={r.error_summary}>⚠ {r.error_summary.slice(0, 60)}</span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="monitor-empty">No run history.</div>
            )}
          </div>

          {/* Recent events */}
          <div className="monitor-section">
            <div className="monitor-section-title">Recent events</div>
            {eventsLoading ? (
              <div className="monitor-loading">Loading…</div>
            ) : events && events.length > 0 ? (
              <div className="monitor-event-list">
                {events.map((ev) => (
                  <div key={ev.id} className="monitor-event-row">
                    <span className={eventSeverityClass(ev.severity)}>{ev.severity}</span>
                    <span className="monitor-ev-time">{timeAgo(ev.created_at)}</span>
                    <span className="monitor-ev-msg">{ev.message}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="monitor-empty">No events recorded.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

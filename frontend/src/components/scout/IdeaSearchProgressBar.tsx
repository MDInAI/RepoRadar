"use client";

import type { IdeaSearchProgressSummary } from "@/api/idea-scout";

interface IdeaSearchProgressBarProps {
  progress: IdeaSearchProgressSummary[];
  direction: "backward" | "forward";
  totalQueries: number;
}

const SCAN_ORIGIN = new Date("2008-01-01").getTime();

function computeOverallPct(progress: IdeaSearchProgressSummary[]): number {
  if (!progress.length) return 0;
  const today = Date.now();
  const totalSpan = today - SCAN_ORIGIN; // today - Jan 2008
  if (totalSpan <= 0) return 100;
  let totalPct = 0;
  for (const p of progress) {
    if (p.exhausted) {
      totalPct += 100;
    } else {
      const cur = new Date(p.window_start_date).getTime();
      const scannedSpan = today - cur; // how far back from today we've scanned
      totalPct += Math.min(100, Math.max(0, (scannedSpan / totalSpan) * 100));
    }
  }
  return Math.round(totalPct / progress.length);
}

function queryStateLabel(p: IdeaSearchProgressSummary): string {
  if (p.exhausted) return "done";
  if (p.consecutive_errors > 0) return "error";
  if (p.resume_required) return "scanning";
  return "pending";
}

function queryStateBadgeClass(p: IdeaSearchProgressSummary): string {
  if (p.exhausted) return "scout-badge scout-badge-completed";
  if (p.consecutive_errors > 0) return "scout-badge scout-badge-error";
  if (p.resume_required) return "scout-badge scout-badge-active";
  return "scout-badge scout-badge-meta";
}

export function IdeaSearchProgressBar({ progress, direction, totalQueries }: IdeaSearchProgressBarProps) {
  if (!progress.length) {
    return <div className="scout-progress-empty-text">Waiting for first scan cycle\u2026</div>;
  }

  const exhaustedCount = progress.filter((item) => item.exhausted).length;
  const errorCount = progress.filter((item) => item.consecutive_errors > 0).length;
  const overallPct = direction === "backward" ? computeOverallPct(progress) : null;

  const dirLabel = direction === "backward"
    ? "Scanning GitHub history from today back to 2008"
    : "Watching for newly created repos";

  return (
    <div className="scout-progress-wrap">
      <div className="scout-progress-info">
        <span>{dirLabel}</span>
        <span className="scout-progress-pct">
          {exhaustedCount}/{totalQueries} queries done
          {errorCount > 0 && <span className="scout-progress-error-hint"> &middot; {errorCount} with errors</span>}
        </span>
      </div>
      {overallPct !== null && (
        <div className="scout-progress-track">
          <div
            className={`scout-progress-fill ${errorCount > 0 ? "scout-progress-fill-warn" : ""}`}
            style={{ width: `${overallPct}%` }}
          />
          <span className="scout-progress-pct-label">{overallPct}%</span>
        </div>
      )}
    </div>
  );
}

export { queryStateLabel, queryStateBadgeClass };

"use client";

import type { IdeaSearchProgressSummary } from "@/api/idea-scout";

interface IdeaSearchProgressBarProps {
  progress: IdeaSearchProgressSummary[];
  direction: "backward" | "forward";
}

export function IdeaSearchProgressBar({ progress, direction }: IdeaSearchProgressBarProps) {
  if (!progress.length) {
    return <span className="text-xs text-neutral-500">No progress yet</span>;
  }

  const exhaustedCount = progress.filter((p) => p.exhausted).length;
  const totalQueries = progress.length;
  const pct = totalQueries > 0 ? Math.round((exhaustedCount / totalQueries) * 100) : 0;

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-neutral-400">
        <span>
          {direction === "backward" ? "Historical scan" : "Forward watch"} &mdash;{" "}
          {exhaustedCount}/{totalQueries} queries done
        </span>
        <span>{pct}%</span>
      </div>
      <div className="h-1.5 bg-neutral-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-indigo-500 rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex flex-wrap gap-1 mt-1">
        {progress.map((p) => (
          <span
            key={p.query_index}
            className={`inline-block w-2 h-2 rounded-full ${
              p.exhausted
                ? "bg-green-500"
                : p.resume_required
                  ? "bg-yellow-500"
                  : "bg-indigo-500 animate-pulse"
            }`}
            title={`Query ${p.query_index}: ${p.window_start_date} → ${p.created_before_boundary}${
              p.exhausted ? " (done)" : ""
            }`}
          />
        ))}
      </div>
    </div>
  );
}

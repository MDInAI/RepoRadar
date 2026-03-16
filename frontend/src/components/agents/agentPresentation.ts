import type {
  AgentName,
  AgentRunEvent,
  AgentRunStatus,
  AgentRuntimeProgress,
  EventSeverity,
} from "@/api/agents";
import { formatAppDateTime } from "@/lib/time";

const RELATIVE_DATE_FORMATTER = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
const INTEGER_FORMATTER = new Intl.NumberFormat("en-US");

const AGENT_LABELS: Record<AgentName, string> = {
  overlord: "Overlord",
  firehose: "Firehose",
  backfill: "Backfill",
  bouncer: "Bouncer",
  analyst: "Analyst",
  combiner: "Combiner",
  obsession: "Obsession",
};

const RUN_STATUS_LABELS: Record<AgentRunStatus, string> = {
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  skipped: "Skipped",
  skipped_paused: "Skipped (Paused)",
};

function titleCaseWords(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatAgentName(agentName: AgentName): string {
  return AGENT_LABELS[agentName];
}

export function formatAgentRunStatus(status: AgentRunStatus): string {
  return RUN_STATUS_LABELS[status];
}

export function formatRelativeTimestamp(value: string | null): string {
  if (!value) {
    return "No recent activity";
  }

  const target = new Date(value);
  if (Number.isNaN(target.getTime())) {
    return "Unknown";
  }

  const diffMs = target.getTime() - Date.now();
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));
  if (Math.abs(diffDays) >= 1) {
    return RELATIVE_DATE_FORMATTER.format(diffDays, "day");
  }

  const diffHours = Math.round(diffMs / (1000 * 60 * 60));
  if (Math.abs(diffHours) >= 1) {
    return RELATIVE_DATE_FORMATTER.format(diffHours, "hour");
  }

  const diffMinutes = Math.round(diffMs / (1000 * 60));
  return RELATIVE_DATE_FORMATTER.format(diffMinutes, "minute");
}

export function formatTimestampLabel(value: string | null): string {
  return formatAppDateTime(value);
}

export function formatRunDuration(durationSeconds: number | null): string {
  if (durationSeconds === null) {
    return "In progress";
  }
  if (durationSeconds < 60) {
    return `${Math.round(durationSeconds)}s`;
  }
  const minutes = Math.floor(durationSeconds / 60);
  const seconds = Math.round(durationSeconds % 60);
  return `${minutes}m ${seconds}s`;
}

export function formatItemsCount(value: number | null): string {
  if (value === null) {
    return "N/A";
  }
  return INTEGER_FORMATTER.format(value);
}

export function formatItemsSummary(run: AgentRunEvent | null): string {
  if (!run) {
    return "No runs captured yet";
  }

  return `${formatItemsCount(run.items_processed)} processed / ${formatItemsCount(
    run.items_succeeded,
  )} ok / ${formatItemsCount(run.items_failed)} failed`;
}

export function formatRuntimeProgressCounts(progress: AgentRuntimeProgress | null | undefined): string {
  if (!progress) {
    return "No live progress snapshot";
  }

  const unitLabel = progress.unit_label ?? "items";
  if (progress.completed_count != null && progress.total_count != null) {
    return `${formatItemsCount(progress.completed_count)} / ${formatItemsCount(progress.total_count)} ${unitLabel}`;
  }
  if (progress.remaining_count != null) {
    return `${formatItemsCount(progress.remaining_count)} ${unitLabel} remaining`;
  }
  return progress.status_label;
}

export function formatRuntimeProgressHeadline(progress: AgentRuntimeProgress | null | undefined): string {
  if (!progress) {
    return "No live runtime snapshot";
  }
  const currentTarget = progress.current_target ? ` ${progress.current_target}` : "";
  return `${progress.current_activity}${currentTarget}`;
}

export function getRunStatusBadgeClassName(
  status: AgentRunStatus | "never_run",
): string {
  if (status === "completed") {
    return "border-emerald-300 bg-emerald-100 text-emerald-900";
  }
  if (status === "running") {
    return "border-amber-300 bg-amber-100 text-amber-900";
  }
  if (status === "failed") {
    return "border-rose-300 bg-rose-100 text-rose-900";
  }
  if (status === "skipped") {
    return "border-slate-300 bg-slate-100 text-slate-800";
  }
  if (status === "skipped_paused") {
    return "border-orange-300 bg-orange-100 text-orange-900";
  }
  return "border-slate-200 bg-white text-slate-500";
}

export function formatSeverityLabel(severity: EventSeverity): string {
  return titleCaseWords(severity);
}

export function getSeverityBadgeClassName(severity: EventSeverity): string {
  if (severity === "critical" || severity === "error") {
    return "border-rose-300 bg-rose-100 text-rose-900";
  }
  if (severity === "warning") {
    return "border-amber-300 bg-amber-100 text-amber-900";
  }
  return "border-sky-300 bg-sky-100 text-sky-900";
}

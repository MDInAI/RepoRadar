import type {
  RepositoryAnalysisStatus,
  RepositoryDiscoverySource,
  RepositoryMonetizationPotential,
} from "@/api/repositories";

const RELATIVE_DATE_FORMATTER = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
const INTEGER_FORMATTER = new Intl.NumberFormat("en-US");

function titleCaseWords(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatCompactNumber(value: number): string {
  return INTEGER_FORMATTER.format(value);
}

export function formatRelativeDate(value: string | null): string {
  if (!value) {
    return "No activity";
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

export function formatDiscoverySourceLabel(value: RepositoryDiscoverySource): string {
  if (value === "firehose") {
    return "Firehose";
  }
  if (value === "backfill") {
    return "Backfill";
  }
  return "Unknown";
}

export function formatAnalysisStatusLabel(value: RepositoryAnalysisStatus): string {
  return titleCaseWords(value);
}

export function formatMonetizationLabel(
  value: RepositoryMonetizationPotential | null,
): string {
  return value ? titleCaseWords(value) : "Unscored";
}

export function getSourceBadgeClassName(value: RepositoryDiscoverySource): string {
  if (value === "firehose") {
    return "border-orange-300 bg-orange-100 text-orange-900";
  }
  if (value === "backfill") {
    return "border-sky-300 bg-sky-100 text-sky-900";
  }
  return "border-slate-300 bg-slate-100 text-slate-800";
}

export function getStatusBadgeClassName(value: RepositoryAnalysisStatus): string {
  if (value === "completed") {
    return "border-emerald-300 bg-emerald-100 text-emerald-900";
  }
  if (value === "in_progress") {
    return "border-amber-300 bg-amber-100 text-amber-900";
  }
  if (value === "failed") {
    return "border-rose-300 bg-rose-100 text-rose-900";
  }
  return "border-slate-300 bg-slate-100 text-slate-800";
}

export function getFitBadgeClassName(
  value: RepositoryMonetizationPotential | null,
): string {
  if (value === "high") {
    return "border-emerald-300 bg-emerald-100 text-emerald-950";
  }
  if (value === "medium") {
    return "border-amber-300 bg-amber-100 text-amber-950";
  }
  if (value === "low") {
    return "border-rose-300 bg-rose-100 text-rose-950";
  }
  return "border-slate-300 bg-slate-100 text-slate-700";
}

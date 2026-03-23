"use client";

import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import {
  fetchRepositoryBacklogSummary,
  getRepositoryBacklogSummaryQueryKey,
  type RepositoryAnalysisStatus,
  type RepositoryCatalogViewState,
  type RepositoryQueueStatus,
  type RepositoryTriageStatus,
} from "@/api/repositories";

import {
  formatAnalysisStatusLabel,
  formatQueueStatusLabel,
  formatTriageStatusLabel,
  getQueueStatusBadgeClassName,
  getStatusBadgeClassName,
  getTriageStatusBadgeClassName,
} from "./catalogPresentation";

type BacklogFilterPatch = Partial<
  Pick<
    RepositoryCatalogViewState,
    "queueStatus" | "triageStatus" | "analysisStatus" | "hasFailures"
  >
>;

function SummaryBadge({
  label,
  count,
  ariaLabel,
  className,
  onClick,
}: {
  label: string;
  count: number;
  ariaLabel: string;
  className: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={ariaLabel}
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition hover:-translate-y-0.5 hover:shadow-sm ${className}`}
      type="button"
      onClick={onClick}
    >
      <span>{label}</span>
      <span className="rounded-full bg-black/5 px-2 py-0.5 text-[11px]">{count}</span>
    </button>
  );
}

function SummaryGroup({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-4 shadow-[0_18px_45px_-36px_rgba(15,23,42,0.5)]">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">{title}</p>
      <div className="mt-3 flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

export function BacklogSummaryBar({
  onSelectFilters,
}: {
  onSelectFilters: (patch: BacklogFilterPatch) => void;
}) {
  const summaryQuery = useQuery({
    queryKey: getRepositoryBacklogSummaryQueryKey(),
    queryFn: fetchRepositoryBacklogSummary,
    staleTime: 30_000,
  });

  if (summaryQuery.isLoading) {
    return (
      <section className="rounded-[2rem] border border-black/10 bg-white/85 px-6 py-5 shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)] backdrop-blur">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
          Processing backlog
        </p>
        <p className="mt-2 text-sm text-slate-600">Loading queue, triage, and analysis counts.</p>
      </section>
    );
  }

  if (summaryQuery.isError || !summaryQuery.data) {
    const message =
      summaryQuery.error instanceof Error
        ? summaryQuery.error.message
        : "Unable to load backlog summary.";
    return (
      <section className="rounded-[2rem] border border-rose-200 bg-rose-50 px-6 py-5 shadow-[0_20px_60px_-36px_rgba(244,63,94,0.35)]">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-rose-700">
          Backlog summary unavailable
        </p>
        <p className="mt-2 text-sm text-rose-900">{message}</p>
      </section>
    );
  }

  const { queue, triage, analysis } = summaryQuery.data;

  const queueStatuses: RepositoryQueueStatus[] = [
    "pending",
    "in_progress",
    "completed",
    "failed",
  ];
  const triageStatuses: RepositoryTriageStatus[] = ["pending", "accepted", "rejected"];
  const analysisStatuses: RepositoryAnalysisStatus[] = [
    "pending",
    "in_progress",
    "completed",
    "failed",
  ];

  return (
    <section className="rounded-[2rem] border border-black/10 bg-white/85 p-5 shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)] backdrop-blur">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
            Processing backlog
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
            Review the pipeline state without leaving the catalog
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Jump straight into queue pressure, triage outcomes, or analysis failures from these
            aggregate status counts.
          </p>
        </div>

        <button
          aria-label="Show failed repositories"
          className="inline-flex h-fit items-center justify-center rounded-full border border-rose-300 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-900 transition hover:bg-rose-100"
          type="button"
          onClick={() => onSelectFilters({ hasFailures: true })}
        >
          Show failures only
        </button>
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-3">
        <SummaryGroup title="Queue">
          {queueStatuses.map((status) => (
            <SummaryBadge
              key={status}
              ariaLabel={`${queue[status]} repositories with ${formatQueueStatusLabel(status).toLowerCase()} queue status`}
              className={getQueueStatusBadgeClassName(status)}
              count={queue[status]}
              label={formatQueueStatusLabel(status)}
              onClick={() => onSelectFilters({ queueStatus: status })}
            />
          ))}
        </SummaryGroup>

        <SummaryGroup title="Triage">
          {triageStatuses.map((status) => (
            <SummaryBadge
              key={status}
              ariaLabel={`${triage[status]} repositories with ${formatTriageStatusLabel(status).toLowerCase()} triage status`}
              className={getTriageStatusBadgeClassName(status)}
              count={triage[status]}
              label={formatTriageStatusLabel(status)}
              onClick={() => onSelectFilters({ triageStatus: status })}
            />
          ))}
        </SummaryGroup>

        <SummaryGroup title="Analysis">
          {analysisStatuses.map((status) => (
            <SummaryBadge
              key={status}
              ariaLabel={`${analysis[status]} repositories with ${formatAnalysisStatusLabel(status).toLowerCase()} analysis`}
              className={getStatusBadgeClassName(status)}
              count={analysis[status]}
              label={formatAnalysisStatusLabel(status)}
              onClick={() => onSelectFilters({ analysisStatus: status })}
            />
          ))}
        </SummaryGroup>
      </div>
    </section>
  );
}

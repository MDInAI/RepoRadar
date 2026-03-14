"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchOverviewSummary, getOverviewSummaryQueryKey } from "@/api/overview";
import {
  fetchAgentPauseStates,
  fetchLatestAgentRuns,
  getAgentPauseStatesQueryKey,
  getLatestAgentRunsQueryKey,
  type AgentName,
} from "@/api/agents";
import { AgentStatusMatrix } from "@/components/agents/AgentStatusMatrix";
import { useEventStream } from "@/hooks/useEventStream";
import Link from "next/link";

function MetricCard({ title, value, subtitle }: { title: string; value: number; subtitle?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <p className="text-xs uppercase tracking-wider text-slate-500">{title}</p>
      <p className="mt-2 text-3xl font-semibold text-slate-900">{value}</p>
      {subtitle && <p className="mt-1 text-xs text-slate-600">{subtitle}</p>}
    </div>
  );
}

export default function OverviewPage() {
  useEventStream();

  const { data, isLoading, error } = useQuery({
    queryKey: getOverviewSummaryQueryKey(),
    queryFn: fetchOverviewSummary,
    refetchInterval: 30_000,
  });

  const latestRunsQuery = useQuery({
    queryKey: getLatestAgentRunsQueryKey(),
    queryFn: fetchLatestAgentRuns,
    staleTime: 30_000,
  });

  const pauseStatesQuery = useQuery({
    queryKey: getAgentPauseStatesQueryKey(),
    queryFn: fetchAgentPauseStates,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  if (error) {
    return (
      <main className="min-h-screen bg-slate-50 px-6 py-10">
        <div className="mx-auto max-w-7xl">
          <div className="rounded-2xl border border-red-200 bg-red-50 px-6 py-4 text-red-900">
            Failed to load overview: {error instanceof Error ? error.message : "Unknown error"}
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-10">
      <div className="mx-auto max-w-7xl space-y-8">
        <header>
          <p className="text-xs font-semibold uppercase tracking-wider text-orange-600">Overview</p>
          <h1 className="mt-2 text-4xl font-semibold text-slate-900">Mission Control</h1>
          <p className="mt-2 text-sm text-slate-600">
            Master monitoring and control surface for pipeline operations
          </p>
        </header>

        {isLoading ? (
          <div className="text-slate-600">Loading...</div>
        ) : data ? (
          <>
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-slate-900">Quick Actions</h2>
              <div className="mt-4 flex flex-wrap gap-3">
                <Link
                  href="/agents"
                  className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Manage Agents
                </Link>
                <Link
                  href="/incidents"
                  className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  View Incidents
                </Link>
                <Link
                  href="/repositories"
                  className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Browse Repositories
                </Link>
              </div>
            </section>

            <AgentStatusMatrix
              agents={latestRunsQuery.data?.agents ?? data.agents.map(a => ({
                agent_name: a.agent_name as AgentName,
                has_run: a.last_run_at !== null,
                latest_run: a.last_run_at ? {
                  id: 0,
                  agent_name: a.agent_name as AgentName,
                  status: a.status as any,
                  started_at: a.last_run_at,
                  completed_at: null,
                  duration_seconds: null,
                  items_processed: null,
                  items_succeeded: null,
                  items_failed: null,
                  error_summary: null,
                } : null,
              }))}
              pauseStates={pauseStatesQuery.data ?? data.agents.map(a => ({
                agent_name: a.agent_name as AgentName,
                is_paused: a.is_paused,
                paused_at: null,
                pause_reason: null,
                resume_condition: null,
                triggered_by_event_id: null,
                resumed_at: null,
                resumed_by: null,
              }))}
              pauseStateStatus={
                pauseStatesQuery.isError
                  ? "unavailable"
                  : pauseStatesQuery.isLoading
                    ? "loading"
                    : "available"
              }
              description="Agent health and control surface for pause/resume operations"
              isLoading={latestRunsQuery.isLoading && !data.agents.length}
              title="Agent Health & Control"
              variant="detail"
            />
            {latestRunsQuery.isError && (
              <div className="rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
                ⚠️ Detailed agent status unavailable. Showing summary data only.
              </div>
            )}
            <section>
              <h2 className="text-lg font-semibold text-slate-900">Ingestion</h2>
              <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <MetricCard title="Total Repositories" value={data.ingestion.total_repositories} />
                <MetricCard title="Pending Intake" value={data.ingestion.pending_intake} />
                <MetricCard title="Firehose" value={data.ingestion.firehose_discovered} />
                <MetricCard title="Backfill" value={data.ingestion.backfill_discovered} />
              </div>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-slate-900">Triage</h2>
              <div className="mt-4 grid gap-4 sm:grid-cols-3">
                <MetricCard title="Pending" value={data.triage.pending} />
                <MetricCard title="Accepted" value={data.triage.accepted} />
                <MetricCard title="Rejected" value={data.triage.rejected} />
              </div>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-slate-900">Analysis</h2>
              <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <MetricCard title="Pending" value={data.analysis.pending} />
                <MetricCard title="In Progress" value={data.analysis.in_progress} />
                <MetricCard title="Completed" value={data.analysis.completed} />
                <MetricCard title="Failed" value={data.analysis.failed} />
              </div>
            </section>

            <section>
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-900">Repository Backlog</h2>
                <Link href="/repositories" className="text-sm text-blue-600 hover:text-blue-800">
                  View All →
                </Link>
              </div>
              <div className="mt-4 space-y-4">
                <div>
                  <h3 className="text-sm font-medium text-slate-700">Queue Status</h3>
                  <div className="mt-2 grid gap-4 sm:grid-cols-4">
                    <MetricCard title="Pending" value={data.backlog.queue_pending} />
                    <MetricCard title="In Progress" value={data.backlog.queue_in_progress} />
                    <MetricCard title="Completed" value={data.backlog.queue_completed} />
                    <MetricCard title="Failed" value={data.backlog.queue_failed} />
                  </div>
                </div>
                <div>
                  <h3 className="text-sm font-medium text-slate-700">Triage Status</h3>
                  <div className="mt-2 grid gap-4 sm:grid-cols-3">
                    <MetricCard title="Pending" value={data.backlog.triage_pending} />
                    <MetricCard title="Accepted" value={data.backlog.triage_accepted} />
                    <MetricCard title="Rejected" value={data.backlog.triage_rejected} />
                  </div>
                </div>
                <div>
                  <h3 className="text-sm font-medium text-slate-700">Analysis Status</h3>
                  <div className="mt-2 grid gap-4 sm:grid-cols-4">
                    <MetricCard title="Pending" value={data.backlog.analysis_pending} />
                    <MetricCard title="In Progress" value={data.backlog.analysis_in_progress} />
                    <MetricCard title="Completed" value={data.backlog.analysis_completed} />
                    <MetricCard title="Failed" value={data.backlog.analysis_failed} />
                  </div>
                </div>
              </div>
            </section>

            <section>
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-900">Failures</h2>
                <Link href="/incidents" className="text-sm text-blue-600 hover:text-blue-800">
                  View Incidents →
                </Link>
              </div>
              <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <MetricCard title="Total" value={data.failures.total_failures} />
                <MetricCard title="Critical" value={data.failures.critical_failures} />
                <MetricCard title="Rate Limited" value={data.failures.rate_limited_failures} />
                <MetricCard title="Blocking" value={data.failures.blocking_failures} />
              </div>
            </section>
          </>
        ) : null}
      </div>
    </main>
  );
}

"use client";

import { useQuery } from "@tanstack/react-query";
import { Component, type ReactNode, useState } from "react";

import {
  fetchAgentPauseStates,
  fetchAgentRuns,
  fetchLatestAgentRuns,
  fetchSystemEvents,
  getAgentPauseStatesQueryKey,
  getAgentRunsQueryKey,
  getLatestAgentRunsQueryKey,
  getSystemEventsQueryKey,
  type AgentName,
  type AgentRunStatus,
} from "@/api/agents";
import { AgentRunHistoryTable } from "@/components/agents/AgentRunHistoryTable";
import { AgentStatusMatrix } from "@/components/agents/AgentStatusMatrix";
import { EventTimeline } from "@/components/agents/EventTimeline";
import { useEventStream } from "@/hooks/useEventStream";

const RUN_PAGE_SIZE = 50;
const MAX_RUN_PAGE_SIZE = 200;

class AgentMonitoringErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    console.error("Agents monitoring surface crashed", error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="min-h-screen bg-[linear-gradient(180deg,#fff8ef_0%,#f8fafc_44%,#e0f2fe_100%)] px-6 py-10 text-slate-900">
          <section className="mx-auto max-w-3xl rounded-[2rem] border border-rose-200 bg-rose-50 px-6 py-6 text-sm text-rose-900 shadow-[0_20px_60px_-36px_rgba(244,63,94,0.35)]">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-rose-700">
              Agents
            </p>
            <h1 className="mt-3 text-2xl font-semibold text-rose-950">
              Monitoring surface failed to render
            </h1>
            <p className="mt-3">
              Refresh the page to reload the monitoring surface. The backend state remains
              unchanged.
            </p>
            <button
              className="mt-5 rounded-full border border-rose-900 bg-rose-900 px-4 py-2 font-semibold text-white transition hover:bg-rose-800"
              type="button"
              onClick={() => window.location.reload()}
            >
              Reload page
            </button>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}

function AgentsClientContent() {
  const [agentFilter, setAgentFilter] = useState<AgentName | null>(null);
  const [statusFilter, setStatusFilter] = useState<AgentRunStatus | null>(null);
  const [runLimit, setRunLimit] = useState(RUN_PAGE_SIZE);
  const stream = useEventStream();

  const handleAgentFilterChange = (value: AgentName | null) => {
    setRunLimit(RUN_PAGE_SIZE);
    setAgentFilter(value);
  };

  const handleStatusFilterChange = (value: AgentRunStatus | null) => {
    setRunLimit(RUN_PAGE_SIZE);
    setStatusFilter(value);
  };

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

  const runsQuery = useQuery({
    queryKey: getAgentRunsQueryKey({
      agent_name: agentFilter,
      status: statusFilter,
      limit: runLimit,
    }),
    queryFn: () =>
      fetchAgentRuns({
        agent_name: agentFilter,
        status: statusFilter,
        limit: runLimit,
      }),
  });

  const eventsQuery = useQuery({
    queryKey: getSystemEventsQueryKey({ limit: 25 }),
    queryFn: () => fetchSystemEvents({ limit: 25 }),
    staleTime: 15_000,
  });

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#fff8ef_0%,#f8fafc_44%,#e0f2fe_100%)] px-6 py-10 text-slate-900">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <header className="rounded-[2.2rem] border border-black/10 bg-white/85 px-6 py-7 shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)] backdrop-blur">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.32em] text-orange-700">
                Agents
              </p>
              <h1 className="mt-3 text-4xl font-semibold tracking-tight text-slate-950">
                Real-time operational status
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-600">
                Monitor current agent state, recent executions, and system events without leaving
                the control surface. All live updates flow through the backend REST and SSE APIs.
              </p>
            </div>

            <div className="rounded-[1.6rem] border border-slate-200 bg-slate-50/90 px-4 py-4 text-sm text-slate-700">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                Stream State
              </p>
              <div
                aria-atomic="true"
                aria-live="polite"
                className="mt-2"
                role="status"
              >
                <span className="sr-only">SSE stream state:</span>
                <p className="font-semibold capitalize text-slate-950">
                  {stream.connectionState}
                </p>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                SSE invalidates cached queries whenever new run or event updates arrive.
              </p>
            </div>
          </div>
        </header>

        {latestRunsQuery.isError ? (
          <section className="rounded-[2rem] border border-rose-200 bg-rose-50 px-6 py-5 text-sm text-rose-900 shadow-[0_20px_60px_-36px_rgba(244,63,94,0.35)]">
            {latestRunsQuery.error instanceof Error
              ? latestRunsQuery.error.message
              : "Unable to load the latest agent status matrix."}
          </section>
        ) : null}

        {pauseStatesQuery.isError ? (
          <section className="rounded-[2rem] border border-amber-200 bg-amber-50 px-6 py-5 text-sm text-amber-900 shadow-[0_20px_60px_-36px_rgba(245,158,11,0.25)]">
            Unable to load agent pause states — pause badges may be missing or outdated.
          </section>
        ) : null}

        {!latestRunsQuery.isError ? (
          <AgentStatusMatrix
            agents={latestRunsQuery.data?.agents ?? []}
            pauseStates={pauseStatesQuery.data ?? []}
            pauseStateStatus={
              pauseStatesQuery.isError
                ? "unavailable"
                : pauseStatesQuery.isLoading
                  ? "loading"
                  : "available"
            }
            description="Current run status per named agent with backend-derived counts and last activity."
            isLoading={latestRunsQuery.isLoading}
            title="Agent Status Matrix"
          />
        ) : null}

        <div className="grid gap-6 xl:grid-cols-[1.8fr_1fr]">
          <div className="space-y-6">
            {runsQuery.isError ? (
              <section className="rounded-[2rem] border border-rose-200 bg-rose-50 px-6 py-5 text-sm text-rose-900 shadow-[0_20px_60px_-36px_rgba(244,63,94,0.35)]">
                {runsQuery.error instanceof Error
                  ? runsQuery.error.message
                  : "Unable to load agent run history."}
              </section>
            ) : (
              <AgentRunHistoryTable
                agentFilter={agentFilter}
                canLoadMore={
                  !runsQuery.isLoading &&
                  runLimit < MAX_RUN_PAGE_SIZE &&
                  (runsQuery.data?.length ?? 0) >= runLimit
                }
                isLoading={runsQuery.isLoading}
                isLoadingMore={runsQuery.isFetching && !runsQuery.isLoading}
                onAgentFilterChange={handleAgentFilterChange}
                onLoadMore={() => {
                  setRunLimit((limit) => Math.min(limit + RUN_PAGE_SIZE, MAX_RUN_PAGE_SIZE));
                }}
                onStatusFilterChange={handleStatusFilterChange}
                runs={runsQuery.data ?? []}
                statusFilter={statusFilter}
              />
            )}
          </div>

          {eventsQuery.isError ? (
            <section className="rounded-[2rem] border border-rose-200 bg-rose-50 px-6 py-5 text-sm text-rose-900 shadow-[0_20px_60px_-36px_rgba(244,63,94,0.35)]">
              {eventsQuery.error instanceof Error
                ? eventsQuery.error.message
                : "Unable to load recent system events."}
            </section>
          ) : (
            <EventTimeline events={eventsQuery.data ?? []} isLoading={eventsQuery.isLoading} />
          )}
        </div>
      </div>
    </main>
  );
}

export default function AgentsClient() {
  return (
    <AgentMonitoringErrorBoundary>
      <AgentsClientContent />
    </AgentMonitoringErrorBoundary>
  );
}

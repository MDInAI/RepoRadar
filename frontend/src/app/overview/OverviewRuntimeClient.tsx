"use client";

import { fetchGatewayRuntime, ReadinessRequestError } from "@/api/readiness";
import type {
  GatewayAgentIntakeQueueSummary,
  GatewayAgentQueue,
  GatewayNamedAgentSummary,
  GatewayRuntimeSurfaceResponse,
} from "@/lib/gateway-contract";
import { startTransition, useEffect, useRef, useState } from "react";

import {
  createRuntimeRefreshController,
  MAX_CONSECUTIVE_REFRESH_FAILURES,
  RUNTIME_REFRESH_INTERVAL_MS,
  type RuntimeRefreshController,
  type RuntimeRefreshSnapshot,
} from "./runtimeRefreshController";
import {
  formatLastUpdatedLabel,
  getPollingIndicatorClassName,
  getPollingStatusAnnouncement,
  getPollingStatusLabel,
} from "./runtimeSyncStatus";
import { renderCheckpointRows } from "./runtimeFormatting";

// Queue.status is the contract discriminator between reserved and live runtime states.
function isLiveIntakeQueue(
  queue: GatewayAgentQueue,
): queue is GatewayAgentIntakeQueueSummary {
  return queue.status === "live";
}

function IntakeCard({
  agent,
  displayTimeZone,
  queue,
  isRefreshing,
}: {
  agent: GatewayNamedAgentSummary;
  displayTimeZone: string;
  queue: GatewayAgentIntakeQueueSummary;
  isRefreshing: boolean;
}) {
  const checkpointRows = renderCheckpointRows(queue, displayTimeZone);

  return (
    <section
      aria-busy={isRefreshing}
      className={`rounded-3xl border border-black/10 bg-white/85 p-6 shadow-[0_20px_60px_-32px_rgba(15,23,42,0.45)] backdrop-blur transition-opacity ${
        isRefreshing ? "opacity-80" : "opacity-100"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-orange-700">
            {agent.display_name} Intake
          </p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-900">
            {queue.total_items} persisted repositories
          </h2>
          <p className="mt-2 max-w-xl text-sm text-slate-600">
            Backend-owned queue counts plus resume metadata for operator verification
            before triage and analysis stories arrive.
          </p>
        </div>
        <div className="rounded-full bg-slate-900 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-white">
          {queue.source_of_truth}
        </div>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ["Pending", queue.state_counts.pending],
          ["In Progress", queue.state_counts.in_progress],
          ["Completed", queue.state_counts.completed],
          ["Failed", queue.state_counts.failed],
        ].map(([label, value]) => (
          <div
            key={label}
            className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"
          >
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">{label}</p>
            <p className="mt-2 text-3xl font-semibold text-slate-900">{value}</p>
          </div>
        ))}
      </div>

      <div className="mt-6 rounded-2xl border border-slate-200 bg-white px-4 py-4">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
          Checkpoint Context
        </p>
        <dl className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2">
          {checkpointRows.map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</dt>
              <dd className="mt-1 text-sm font-medium text-slate-800">{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      {queue.notes && queue.notes.length > 0 && (
        <div className="mt-6 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-800">
            Backend Notes
          </p>
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-blue-900">
            {queue.notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function AgentMatrix({
  runtime,
}: {
  runtime: GatewayRuntimeSurfaceResponse["runtime"];
}) {
  return (
    <section className="rounded-3xl border border-black/10 bg-slate-950 px-6 py-6 text-white shadow-[0_24px_70px_-36px_rgba(15,23,42,0.8)]">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-orange-300">
            Agent Matrix
          </p>
          <h2 className="mt-2 text-2xl font-semibold">Runtime ownership stays backend-mediated</h2>
        </div>
        <p className="max-w-xl text-sm text-slate-300">
          Queue status is live only for intake agents in Story 2.6. Session affinity and reserved
          monitoring placeholders remain on the same normalized Gateway surface.
        </p>
      </div>

      <div className="mt-6 grid gap-3">
        {runtime.agent_states.map((agent) => {
          const queueLabel = isLiveIntakeQueue(agent.queue)
            ? `${agent.queue.total_items} total`
            : "Reserved";

          return (
            <div
              key={agent.agent_key}
              className="grid gap-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-4 sm:grid-cols-[1.2fr_1fr_1fr_1fr]"
            >
              <div>
                <p className="text-lg font-semibold">{agent.display_name}</p>
                <p className="text-sm text-slate-300">{agent.agent_role}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Lifecycle</p>
                <p className="mt-1 text-sm text-slate-100">{agent.lifecycle_state}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Queue</p>
                <p className="mt-1 text-sm text-slate-100">{queueLabel}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Session Route</p>
                <p className="mt-1 text-sm text-slate-100">
                  {agent.session_affinity.route_key ?? "Reserved"}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function formatRefreshError(error: unknown): string {
  return error instanceof ReadinessRequestError
    ? error.message
    : "Unable to refresh backend-owned intake status.";
}

const INITIAL_REFRESH_SNAPSHOT: RuntimeRefreshSnapshot = {
  refreshInFlight: false,
  consecutiveFailures: 0,
  pollingPaused: false,
};

export function OverviewRuntimeClient({
  initialRuntime,
  initialError,
  initialUpdatedAt,
}: {
  initialRuntime: GatewayRuntimeSurfaceResponse | null;
  initialError?: string | null;
  initialUpdatedAt: string | null;
}) {
  const [runtime, setRuntime] = useState(initialRuntime);
  const [lastUpdatedAt, setLastUpdatedAt] = useState(initialUpdatedAt);
  const [refreshError, setRefreshError] = useState<string | null>(initialError ?? null);
  const [refreshSnapshot, setRefreshSnapshot] = useState(INITIAL_REFRESH_SNAPSHOT);
  const [displayTimeZone, setDisplayTimeZone] = useState("UTC");
  const mountedRef = useRef(false);
  const refreshControllerRef = useRef<RuntimeRefreshController | null>(null);

  const applyClientState = (updater: () => void) => {
    if (!mountedRef.current) {
      return;
    }

    startTransition(() => {
      if (mountedRef.current) {
        updater();
      }
    });
  };

  useEffect(() => {
    mountedRef.current = true;
    setDisplayTimeZone(
      Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    );

    const refreshController = createRuntimeRefreshController({
      intervalMs: RUNTIME_REFRESH_INTERVAL_MS,
      maxConsecutiveFailures: MAX_CONSECUTIVE_REFRESH_FAILURES,
      scheduler: {
        setInterval(callback, delayMs) {
          return window.setInterval(callback, delayMs);
        },
        clearInterval(intervalId) {
          window.clearInterval(intervalId);
        },
      },
      visibilitySource: {
        getVisibilityState() {
          return document.visibilityState;
        },
        addEventListener(eventName, listener) {
          document.addEventListener(eventName, listener);
        },
        removeEventListener(eventName, listener) {
          document.removeEventListener(eventName, listener);
        },
      },
      onStateChange(snapshot) {
        applyClientState(() => {
          setRefreshSnapshot(snapshot);
        });
      },
      async onRefreshRequest() {
        try {
          const nextRuntime = await fetchGatewayRuntime();
          const refreshedAt = new Date().toISOString();
          applyClientState(() => {
            setRuntime(nextRuntime);
            setLastUpdatedAt(refreshedAt);
            setRefreshError(null);
          });
          return true;
        } catch (error) {
          applyClientState(() => {
            setRefreshError(formatRefreshError(error));
          });
          return false;
        }
      },
    });

    refreshControllerRef.current = refreshController;
    refreshController.start();

    return () => {
      mountedRef.current = false;
      refreshController.stop();
      refreshControllerRef.current = null;
    };
  }, []);

  const handleRetryNow = () => {
    void refreshControllerRef.current?.triggerManualRefresh();
  };

  const firehoseAgent = runtime?.runtime.agent_states.find(
    (agent) => agent.agent_key === "firehose" && isLiveIntakeQueue(agent.queue),
  );
  const backfillAgent = runtime?.runtime.agent_states.find(
    (agent) => agent.agent_key === "backfill" && isLiveIntakeQueue(agent.queue),
  );
  const hasSuccessfulSnapshot = runtime !== null && lastUpdatedAt !== null;

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#fff7ed_0%,#f8fafc_42%,#e0f2fe_100%)] px-6 py-10 text-slate-900">
      <div className="mx-auto flex max-w-6xl flex-col gap-8">
        <header className="rounded-[2rem] border border-black/10 bg-white/80 px-6 py-7 shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)] backdrop-blur">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.32em] text-orange-700">
                Overview
              </p>
              <h1 className="mt-3 text-4xl font-semibold tracking-tight text-slate-950">
                Pipeline Flow
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-600">
                Inspect Firehose and Backfill intake state through the backend-owned Gateway
                runtime contract. The browser still talks only to{" "}
                <code>/api/v1/gateway/runtime</code>; queue counts come from Agentic-Workflow
                persistence, while routing metadata remains backend-mediated.
              </p>
            </div>

            <section className="min-w-[16rem] rounded-2xl border border-slate-200 bg-slate-50/90 px-4 py-4 text-sm text-slate-700">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                Live Runtime Sync
              </p>
              <p className="mt-2 font-medium text-slate-900">
                Auto-refresh every 15 seconds
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Last updated {formatLastUpdatedLabel(lastUpdatedAt, displayTimeZone)}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Times shown in {displayTimeZone}
              </p>
              <div
                aria-atomic="true"
                aria-live="polite"
                className="mt-3 flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-orange-700"
                role="status"
              >
                <span className="sr-only">
                  Polling status:{" "}
                  {getPollingStatusAnnouncement(refreshSnapshot, hasSuccessfulSnapshot)}
                </span>
                <span
                  aria-hidden="true"
                  className={`inline-flex h-2.5 w-2.5 rounded-full ${getPollingIndicatorClassName(
                    refreshSnapshot,
                    hasSuccessfulSnapshot,
                  )}`}
                />
                <span>{getPollingStatusLabel(refreshSnapshot, hasSuccessfulSnapshot)}</span>
              </div>
              {refreshSnapshot.consecutiveFailures > 0 ? (
                <p className="mt-2 text-xs text-slate-500">
                  Consecutive refresh failures: {refreshSnapshot.consecutiveFailures}/
                  {MAX_CONSECUTIVE_REFRESH_FAILURES}
                </p>
              ) : null}
            </section>
          </div>

          {refreshError ? (
            <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
              <div>
                {!runtime
                  ? "The initial runtime load failed. The polling loop will keep retrying automatically."
                  : refreshSnapshot.pollingPaused
                    ? "Live refresh paused after repeated failures. Showing the last successful backend snapshot."
                    : "Live refresh is temporarily unavailable. Showing the last successful backend snapshot."}
              </div>
              <div className="mt-1 text-amber-800">{refreshError}</div>
              <div className="mt-3 flex items-center gap-3">
                <button
              aria-busy={refreshSnapshot.refreshInFlight}
              className="rounded-full bg-amber-900 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-white disabled:cursor-not-allowed disabled:bg-amber-300"
              disabled={refreshSnapshot.refreshInFlight}
              onClick={handleRetryNow}
                  type="button"
                >
                  {refreshSnapshot.refreshInFlight ? "Retrying" : "Retry now"}
                </button>
                {refreshSnapshot.pollingPaused ? (
                  <span className="text-xs text-amber-800">
                    Automatic polling resumes after a successful retry.
                  </span>
                ) : null}
              </div>
            </div>
          ) : null}
        </header>

        {runtime ? (
          <>
            <section
              aria-busy={refreshSnapshot.refreshInFlight}
              className="grid gap-6 xl:grid-cols-2"
            >
              {firehoseAgent && isLiveIntakeQueue(firehoseAgent.queue) ? (
                <IntakeCard
                  agent={firehoseAgent}
                  displayTimeZone={displayTimeZone}
                  isRefreshing={refreshSnapshot.refreshInFlight}
                  queue={firehoseAgent.queue}
                />
              ) : null}
              {backfillAgent && isLiveIntakeQueue(backfillAgent.queue) ? (
                <IntakeCard
                  agent={backfillAgent}
                  displayTimeZone={displayTimeZone}
                  isRefreshing={refreshSnapshot.refreshInFlight}
                  queue={backfillAgent.queue}
                />
              ) : null}
            </section>

            <AgentMatrix runtime={runtime.runtime} />
          </>
        ) : null}
      </div>
    </main>
  );
}

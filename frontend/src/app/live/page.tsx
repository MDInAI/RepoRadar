"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo } from "react";

import {
  AGENT_DISPLAY_ORDER,
  fetchAgentPauseStates,
  fetchFailureEvents,
  fetchLatestAgentRuns,
  fetchSystemEvents,
  getAgentPauseStatesQueryKey,
  getFailureEventsQueryKey,
  getLatestAgentRunsQueryKey,
  getSystemEventsQueryKey,
  sortAgentStatusEntries,
  type AgentName,
  type AgentPauseState,
  type AgentRuntimeProgress,
  type AgentStatusEntry,
  type FailureEventPayload,
} from "@/api/agents";
import { fetchOverviewSummary, getOverviewSummaryQueryKey } from "@/api/overview";
import { fetchGatewayRuntime } from "@/api/readiness";
import { EventTimeline } from "@/components/agents/EventTimeline";
import { GeminiKeyPoolPanel } from "@/components/agents/GeminiKeyPoolPanel";
import { GitHubBudgetPanel } from "@/components/agents/GitHubBudgetPanel";
import { OperationalAlertsPanel } from "@/components/agents/OperationalAlertsPanel";
import { AcceptedAnalysisQueuePanel } from "@/components/agents/AcceptedAnalysisQueuePanel";
import {
  buildLatestActiveFailureByAgent,
  isAgentEffectivelyRunning,
} from "@/components/agents/alertState";
import {
  formatAgentName,
  formatAgentRunStatus,
  formatItemsSummary,
  formatRunOrRuntimeSummary,
  formatRelativeTimestamp,
  formatRuntimeProgressCounts,
  formatRuntimeProgressHeadline,
  formatRuntimeSecondaryCounts,
  getRunStatusBadgeClassName,
} from "@/components/agents/agentPresentation";
import { useEventStream } from "@/hooks/useEventStream";
import type {
  GatewayAgentIntakeQueueSummary,
  GatewayAgentQueue,
  GatewayNamedAgentSummary,
} from "@/lib/gateway-contract";

function isLiveIntakeQueue(queue: GatewayAgentQueue): queue is GatewayAgentIntakeQueueSummary {
  return queue.status === "live";
}

function getConnectionBadgeClassName(state: "connecting" | "open" | "closed" | "error"): string {
  if (state === "open") {
    return "badge badge-green";
  }
  if (state === "connecting") {
    return "badge badge-yellow";
  }
  if (state === "error") {
    return "badge badge-red";
  }
  return "badge badge-muted";
}

function getConnectionLabel(state: "connecting" | "open" | "closed" | "error"): string {
  if (state === "open") {
    return "Live stream connected";
  }
  if (state === "connecting") {
    return "Connecting";
  }
  if (state === "error") {
    return "Stream reconnecting";
  }
  return "Stream paused";
}

function getAgentLiveBadge(entry: AgentStatusEntry, pauseState: AgentPauseState | undefined): {
  label: string;
  className: string;
} {
  if (pauseState?.is_paused) {
    return { label: "Paused", className: "badge badge-red" };
  }
  if (isAgentEffectivelyRunning(entry, pauseState)) {
    return { label: "Running", className: "badge badge-yellow" };
  }
  if (entry.runtime_progress?.updated_at) {
    return { label: "Live", className: "badge badge-blue" };
  }
  if (entry.latest_run?.status === "failed") {
    return { label: "Needs attention", className: "badge badge-red" };
  }
  if (entry.latest_run?.status === "completed") {
    return { label: "Standing by", className: "badge badge-green" };
  }
  return { label: "No recent run", className: "badge badge-muted" };
}

function isAgentActive(entry: AgentStatusEntry, pauseState: AgentPauseState | undefined): boolean {
  if (pauseState?.is_paused) {
    return true;
  }
  if (isAgentEffectivelyRunning(entry, pauseState)) {
    return true;
  }
  if (!entry.runtime_progress?.updated_at) {
    return false;
  }
  const updatedAtMs = Date.parse(entry.runtime_progress.updated_at);
  if (Number.isNaN(updatedAtMs)) {
    return false;
  }
  return Date.now() - updatedAtMs <= 15 * 60 * 1000;
}

function progressBar(progress: AgentRuntimeProgress | null | undefined) {
  if (progress?.progress_percent == null) {
    return null;
  }
  return (
    <div className="progress" style={{ marginTop: "8px" }}>
      <div
        className="progress-bar"
        style={{
          width: `${Math.max(0, Math.min(progress.progress_percent, 100))}%`,
          background: "var(--orange)",
        }}
      />
    </div>
  );
}

function renderRuntimeQueue(
  agentName: AgentName,
  agent: GatewayNamedAgentSummary | undefined,
) {
  if (!agent || !isLiveIntakeQueue(agent.queue)) {
    if (agentName === "analyst") {
      return "Analyst uses a run-progress snapshot instead of an intake queue checkpoint.";
    }
    return "No live queue checkpoint";
  }
  return `${agent.queue.pending_items.toLocaleString()} pending of ${agent.queue.total_items.toLocaleString()} total`;
}

function formatRetryWindow(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) {
    return "the current provider retry window";
  }
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (remainingSeconds > 0) {
    return `${minutes}m ${remainingSeconds}s`;
  }
  return `${minutes}m`;
}

function getLatestRunBadge(entry: AgentStatusEntry): { label: string; className: string } {
  if (!entry.latest_run) {
    return { label: "No run recorded", className: "badge badge-muted" };
  }
  return {
    label: `Last run: ${formatAgentRunStatus(entry.latest_run.status)}`,
    className: `badge ${getRunStatusBadgeClassName(entry.latest_run.status)}`,
  };
}

function describeCurrentState(
  entry: AgentStatusEntry,
  pauseState: AgentPauseState | undefined,
  failureEvent: FailureEventPayload | undefined,
): string {
  if (pauseState?.is_paused) {
    if (failureEvent?.failure_classification === "rate_limited" && failureEvent.upstream_provider === "github") {
      return "Paused right now. Nothing is processing because GitHub temporarily blocked API requests.";
    }
    if (failureEvent?.failure_classification === "rate_limited" && failureEvent.upstream_provider !== "github") {
      return "Paused right now. Nothing is processing because the model provider throttled Analyst.";
    }
    return "Paused right now. Nothing is processing until you resume this agent manually.";
  }

  if (isAgentEffectivelyRunning(entry, pauseState)) {
    return "Actively processing work right now.";
  }

  if (entry.runtime_progress?.current_activity) {
    return "Not actively crunching work right now; waiting for the next eligible unit of work.";
  }

  return "Idle right now.";
}

function describeLastRunOutcome(entry: AgentStatusEntry): string {
  if (!entry.latest_run) {
    return "No captured run yet.";
  }
  if (entry.latest_run.status === "completed") {
    return `The last completed run finished successfully: ${formatItemsSummary(entry.latest_run)}.`;
  }
  if (entry.latest_run.status === "running") {
    return `The current run is still active: ${formatRunOrRuntimeSummary(entry.latest_run, entry.runtime_progress)}.`;
  }
  if (entry.latest_run.status === "skipped_paused") {
    return "The latest attempted run did not start because the agent was already paused.";
  }
  if (entry.latest_run.status === "skipped") {
    return "The latest run was skipped and did not process work.";
  }
  if (entry.latest_run.status === "failed") {
    return `The latest run failed: ${formatItemsSummary(entry.latest_run)}.`;
  }
  return `Latest run outcome: ${formatAgentRunStatus(entry.latest_run.status)}.`;
}

function describeProgressMeaning(
  entry: AgentStatusEntry,
  pauseState: AgentPauseState | undefined,
): string {
  const counts = formatRuntimeProgressCounts(entry.runtime_progress);
  const secondaryCounts = formatRuntimeSecondaryCounts(entry.runtime_progress);

  if (pauseState?.is_paused && entry.latest_run?.status === "completed") {
    return `${counts} describes the current blocked checkpoint, not the earlier successful run. ${secondaryCounts ? `${secondaryCounts} still reflects the overall corpus state. ` : ""}The agent completed its last run, then became paused afterward.`;
  }

  if (pauseState?.is_paused && entry.latest_run?.status === "skipped_paused") {
    return `${counts} describes where the agent would resume after you unpause it. ${secondaryCounts ? `${secondaryCounts} is the overall corpus state. ` : ""}No work is being processed right now.`;
  }

  if (!pauseState?.is_paused && entry.latest_run?.status === "completed") {
    return `${counts} is the next waiting checkpoint, not an active run. ${secondaryCounts ? `${secondaryCounts} is the overall corpus state. ` : ""}The last run already finished.`;
  }

  return `${counts} is the best live checkpoint snapshot currently available.${secondaryCounts ? ` ${secondaryCounts}.` : ""}`;
}

function describeRecommendedAction(
  entry: AgentStatusEntry,
  pauseState: AgentPauseState | undefined,
  failureEvent: FailureEventPayload | undefined,
): string {
  if (pauseState?.is_paused) {
    if (failureEvent?.failure_classification === "rate_limited" && failureEvent.upstream_provider === "github") {
      if (failureEvent.retry_after_seconds != null && failureEvent.retry_after_seconds > 0) {
        return `Wait ${formatRetryWindow(failureEvent.retry_after_seconds)}, then resume this agent manually from Control.`;
      }
      return "GitHub did not provide an exact retry time. Wait a bit longer, then do one manual resume from Control.";
    }
    if (entry.agent_name === "analyst") {
      return "Open Incidents, inspect the blocking Analyst failure, then resume Analyst manually from Control.";
    }
    return "Review the pause reason, then resume this agent manually from Control.";
  }

  if (isAgentEffectivelyRunning(entry, pauseState)) {
    return "Watch progress here; no operator action is needed unless an alert appears.";
  }

  if (entry.latest_run?.status === "failed") {
    if (entry.agent_name === "analyst") {
      return "Review the latest Analyst alert, then rerun Analyst after the validation or provider issue is resolved.";
    }
    return "Review the latest alert before rerunning this agent.";
  }

  if (entry.agent_name === "bouncer") {
    return "No action needed unless new repositories enter triage.";
  }

  return "No immediate action needed. This agent is waiting for the next eligible workload.";
}

function needsAttention(
  entry: AgentStatusEntry,
  pauseState: AgentPauseState | undefined,
  failureEvent: FailureEventPayload | undefined,
): boolean {
  return Boolean(pauseState?.is_paused || failureEvent || entry.latest_run?.status === "failed");
}

function isRunningNow(entry: AgentStatusEntry, pauseState: AgentPauseState | undefined): boolean {
  return isAgentEffectivelyRunning(entry, pauseState);
}

function deriveNextActions({
  overview,
  agents,
  pauseStates,
  failureEvents,
}: {
  overview: Awaited<ReturnType<typeof fetchOverviewSummary>> | undefined;
  agents: AgentStatusEntry[];
  pauseStates: AgentPauseState[];
  failureEvents: FailureEventPayload[];
}): string[] {
  const actions: string[] = [];
  const pauseMap = new Map(pauseStates.map((state) => [state.agent_name, state]));
  const latestFailureByAgent = buildLatestActiveFailureByAgent(failureEvents, agents, pauseStates);

  const analyst = agents.find((agent) => agent.agent_name === "analyst");
  const bouncer = agents.find((agent) => agent.agent_name === "bouncer");
  const firehose = agents.find((agent) => agent.agent_name === "firehose");
  const backfill = agents.find((agent) => agent.agent_name === "backfill");
  const analystPause = pauseMap.get("analyst");
  const analystFailure = latestFailureByAgent.get("analyst");

  if (analystPause?.is_paused) {
    if (
      analystFailure?.failure_classification === "rate_limited" &&
      analystFailure.upstream_provider !== "github"
    ) {
      actions.push(
        `Analyst is paused by an LLM/provider rate limit. Wait ${formatRetryWindow(
          analystFailure.retry_after_seconds,
        )}, then resume Analyst manually from Control.`,
      );
    } else {
      actions.push(
        `Analyst is paused. It will not resume by itself. Resolve the pause reason, then resume it manually from Control.`,
      );
    }
  }

  if (pauseStates.some((state) => state.is_paused)) {
    for (const state of pauseStates.filter((item) => item.is_paused && item.agent_name !== "analyst")) {
      actions.push(
        `${formatAgentName(state.agent_name)} is paused. It will not resume by itself; resume it manually after review.`,
      );
    }
  }

  for (const [agentName, event] of latestFailureByAgent.entries()) {
    if (event.failure_classification === "rate_limited") {
      if (agentName === "analyst" && event.upstream_provider === "github") {
        actions.push(
          `Analyst hit a GitHub rate limit. That does not pause Analyst by itself. The run stops early, leaves remaining repos pending, and you can run Analyst again after ${formatRetryWindow(
            event.retry_after_seconds,
          )}.`,
        );
        continue;
      }
      if (agentName === "analyst" && event.upstream_provider !== "github" && analystPause?.is_paused) {
        continue;
      }
      actions.push(
        `${formatAgentName(agentName)} is rate limited. Wait ${formatRetryWindow(
          event.retry_after_seconds,
        )} before forcing another manual run.`,
      );
    }
  }

  if ((overview?.triage.pending ?? 0) > 0 && !isAgentEffectivelyRunning(bouncer, pauseMap.get("bouncer"))) {
    actions.push(
      `Bouncer has ${overview?.triage.pending?.toLocaleString() ?? "pending"} repositories waiting for triage. Run or verify Bouncer next.`,
    );
  }

  if ((overview?.analysis.pending ?? 0) > 0 && !isAgentEffectivelyRunning(analyst, pauseMap.get("analyst"))) {
    actions.push(
      `Analyst has ${overview?.analysis.pending?.toLocaleString() ?? "pending"} accepted repositories waiting for analysis. Resume or run Analyst next.`,
    );
  }

  if (
    (overview?.ingestion.pending_intake ?? 0) > 0 &&
    !isAgentEffectivelyRunning(firehose, pauseMap.get("firehose")) &&
    !isAgentEffectivelyRunning(backfill, pauseMap.get("backfill"))
  ) {
    actions.push(
      `There are ${overview?.ingestion.pending_intake?.toLocaleString() ?? "pending"} repositories still waiting in intake. Confirm whether Firehose or Backfill should move next.`,
    );
  }

  if ((overview?.analysis.completed ?? 0) > 0) {
    actions.push(
      "Use Repositories to review strong analyzed repos, favorite the best candidates, and move promising clusters into Ideas for synthesis.",
    );
  }

  return Array.from(new Set(actions)).slice(0, 6);
}

function buildStrategicBlindSpots(): string[] {
  return [
    "No operator-grade favorites funnel yet. You can star repos, but there is no first-class surface that tracks favorites from discovery through idea synthesis.",
    "No taxonomy quality-review queue yet. Categories and agent tags are generated, but there is no dedicated place to audit low-confidence or contradictory classifications.",
    "No opportunity shortlist lane yet. The system finds repos, but it still lacks a purpose-built board for 'best monetizable candidates right now'.",
    "No cross-agent dependency explanation surface yet. Operators still have to infer why one backlog is growing based on data spread across multiple pages.",
  ];
}

function AgentLiveCard({
  entry,
  pauseState,
  failureEvent,
  runtimeAgent,
}: {
  entry: AgentStatusEntry;
  pauseState: AgentPauseState | undefined;
  failureEvent: FailureEventPayload | undefined;
  runtimeAgent: GatewayNamedAgentSummary | undefined;
}) {
  const liveBadge = getAgentLiveBadge(entry, pauseState);
  const latestRunBadge = getLatestRunBadge(entry);
  const progressHeadline =
    formatRuntimeProgressHeadline(entry.runtime_progress) || formatItemsSummary(entry.latest_run);
  const currentState = describeCurrentState(entry, pauseState, failureEvent);
  const lastRunOutcome = describeLastRunOutcome(entry);
  const progressMeaning = describeProgressMeaning(entry, pauseState);
  const recommendedAction = describeRecommendedAction(entry, pauseState, failureEvent);

  return (
    <article
      className="card"
      style={{
        padding: "14px",
        borderColor: pauseState?.is_paused
          ? "rgba(217, 79, 79, 0.28)"
          : failureEvent
            ? "rgba(217, 166, 58, 0.28)"
            : "var(--border)",
      }}
    >
      <div className="card-header" style={{ alignItems: "flex-start", marginBottom: "10px" }}>
        <div>
          <div className="card-title">{formatAgentName(entry.agent_name)}</div>
          <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
            {entry.role_label}
          </div>
        </div>
        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", justifyContent: "flex-end" }}>
          <span className={liveBadge.className}>{liveBadge.label}</span>
          <span className={latestRunBadge.className}>{latestRunBadge.label}</span>
        </div>
      </div>

      <div style={{ display: "grid", gap: "10px" }}>
        <div>
          <div className="card-label">Current State</div>
          <div style={{ marginTop: "4px", color: "var(--text-0)" }}>{currentState}</div>
        </div>

        <div>
          <div className="card-label">What It Would Do Next</div>
          <div style={{ marginTop: "4px", color: "var(--text-0)" }}>{progressHeadline}</div>
          <div style={{ marginTop: "4px", color: "var(--text-2)", fontSize: "12px" }}>
            {progressMeaning}
          </div>
          {progressBar(entry.runtime_progress)}
        </div>

        <div style={{ display: "grid", gap: "8px", gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          <div>
            <div className="card-label">Current Run Scope</div>
            <div style={{ marginTop: "4px", color: "var(--text-1)" }}>
              {formatRuntimeProgressCounts(entry.runtime_progress)}
            </div>
          </div>
          <div>
            <div className="card-label">Overall Corpus</div>
            <div style={{ marginTop: "4px", color: "var(--text-1)" }}>
              {formatRuntimeSecondaryCounts(entry.runtime_progress) ?? "Unavailable"}
            </div>
          </div>
          <div>
            <div className="card-label">Next Target</div>
            <div style={{ marginTop: "4px", color: "var(--text-1)" }}>
              {entry.runtime_progress?.current_target ?? "No active target"}
            </div>
          </div>
          <div>
            <div className="card-label">Queue Snapshot</div>
            <div style={{ marginTop: "4px", color: "var(--text-1)" }}>
              {renderRuntimeQueue(entry.agent_name, runtimeAgent)}
            </div>
          </div>
          <div>
            <div className="card-label">Last Update</div>
            <div style={{ marginTop: "4px", color: "var(--text-1)" }}>
              {entry.runtime_progress?.updated_at
                ? formatRelativeTimestamp(entry.runtime_progress.updated_at)
                : formatRelativeTimestamp(entry.latest_run?.started_at ?? null)}
            </div>
          </div>
          <div>
            <div className="card-label">Last Run Outcome</div>
            <div style={{ marginTop: "4px", color: "var(--text-1)" }}>
              {lastRunOutcome}
            </div>
          </div>
        </div>

        {entry.notes.length > 0 ? (
          <div>
            <div className="card-label">Agent Notes</div>
            <div style={{ marginTop: "4px", color: "var(--text-2)", fontSize: "12px" }}>
              {entry.notes[0]}
            </div>
          </div>
        ) : null}

        <div
          style={{
            borderRadius: "8px",
            padding: "10px",
            background: "var(--bg-3)",
            color: "var(--text-1)",
          }}
        >
          <div className="card-label">Recommended Action</div>
          <div style={{ marginTop: "4px" }}>{recommendedAction}</div>
        </div>

        {pauseState?.is_paused ? (
          <div
            style={{
              borderRadius: "8px",
              padding: "10px",
              background: "var(--red-dim)",
              color: "var(--text-1)",
            }}
          >
            <div className="card-label" style={{ color: "var(--red)" }}>
              Pause Reason
            </div>
            <div style={{ marginTop: "4px" }}>
              {pauseState.pause_reason ?? "Pause active, but no reason was recorded."}
            </div>
          </div>
        ) : null}

        {!pauseState?.is_paused && failureEvent ? (
          <div
            style={{
              borderRadius: "8px",
              padding: "10px",
              background: "var(--yellow-dim)",
              color: "var(--text-1)",
            }}
          >
            <div className="card-label" style={{ color: "var(--yellow)" }}>
              Latest Alert
            </div>
            <div style={{ marginTop: "4px" }}>{failureEvent.message}</div>
          </div>
        ) : null}
      </div>
    </article>
  );
}

export default function LiveOpsPage() {
  const recentFailureSince = useMemo(
    () => new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    [],
  );
  const recentEventSince = useMemo(
    () => new Date(Date.now() - 6 * 60 * 60 * 1000).toISOString(),
    [],
  );

  const { connectionState } = useEventStream();

  const latestRunsQuery = useQuery({
    queryKey: getLatestAgentRunsQueryKey(),
    queryFn: fetchLatestAgentRuns,
    staleTime: 15_000,
    refetchInterval: 15_000,
  });

  const pauseStatesQuery = useQuery({
    queryKey: getAgentPauseStatesQueryKey(),
    queryFn: fetchAgentPauseStates,
    staleTime: 15_000,
    refetchInterval: 15_000,
  });

  const failureEventsQuery = useQuery({
    queryKey: getFailureEventsQueryKey({ since: recentFailureSince, limit: 12 }),
    queryFn: () => fetchFailureEvents({ since: recentFailureSince, limit: 12 }),
    staleTime: 10_000,
    refetchInterval: 10_000,
  });

  const eventsQuery = useQuery({
    queryKey: getSystemEventsQueryKey({ since: recentEventSince, limit: 25 }),
    queryFn: () => fetchSystemEvents({ since: recentEventSince, limit: 25 }),
    staleTime: 10_000,
    refetchInterval: 10_000,
  });

  const overviewQuery = useQuery({
    queryKey: getOverviewSummaryQueryKey(),
    queryFn: fetchOverviewSummary,
    staleTime: 15_000,
    refetchInterval: 15_000,
  });

  const gatewayRuntimeQuery = useQuery({
    queryKey: ["gateway", "runtime"],
    queryFn: fetchGatewayRuntime,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const agents = latestRunsQuery.data?.agents ?? [];
  const pauseStates = pauseStatesQuery.data ?? [];
  const failureEvents = failureEventsQuery.data ?? [];
  const systemEvents = eventsQuery.data ?? [];
  const overview = overviewQuery.data;
  const gatewayRuntime = gatewayRuntimeQuery.data?.runtime.agent_states ?? [];

  const pauseMap = new Map(pauseStates.map((state) => [state.agent_name, state]));
  const latestFailureByAgent = buildLatestActiveFailureByAgent(failureEvents, agents, pauseStates);
  const gatewayAgentMap = new Map(gatewayRuntime.map((agent) => [agent.agent_key, agent]));

  const sortedAgents = sortAgentStatusEntries(agents);
  const attentionAgents = sortedAgents.filter((entry) =>
    needsAttention(entry, pauseMap.get(entry.agent_name), latestFailureByAgent.get(entry.agent_name)),
  );
  const attentionAgentNames = new Set(attentionAgents.map((entry) => entry.agent_name));
  const runningAgents = sortedAgents.filter(
    (entry) =>
      !attentionAgentNames.has(entry.agent_name) &&
      isRunningNow(entry, pauseMap.get(entry.agent_name)),
  );
  const readyAgents = sortedAgents.filter((entry) => {
    if (attentionAgents.some((item) => item.agent_name === entry.agent_name)) {
      return false;
    }
    if (runningAgents.some((item) => item.agent_name === entry.agent_name)) {
      return false;
    }
    return true;
  });
  const nextActions = deriveNextActions({
    overview,
    agents: sortedAgents,
    pauseStates,
    failureEvents,
  });
  const blindSpots = buildStrategicBlindSpots();
  const activeCount = runningAgents.length;
  const pausedCount = pauseStates.filter((state) => state.is_paused).length;
  const attentionCount = attentionAgents.length;

  const loading = latestRunsQuery.isLoading && overviewQuery.isLoading;

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Live Ops</span>
        <span style={{ color: "var(--text-2)", fontSize: "12px" }}>
          real-time command surface
        </span>
      </div>

      <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden", padding: "20px" }}>
        <section className="hero-strip" style={{ alignItems: "flex-start", gap: "18px", flexWrap: "wrap" }}>
          <div style={{ minWidth: 0, flex: "1 1 420px" }}>
            <div className="card-label">Operator Mission</div>
            <h2 style={{ marginTop: "8px", fontSize: "24px", fontWeight: 700, color: "var(--text-0)" }}>
              One place to see what every agent is doing right now
            </h2>
            <p style={{ marginTop: "8px", color: "var(--text-2)", maxWidth: "900px" }}>
              This view is optimized for your real workflow: keep intake moving, verify taxonomy quality,
              spot strong monetizable repositories, favorite the best candidates, and push good clusters
              into idea synthesis.
            </p>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "12px" }}>
              <span className={getConnectionBadgeClassName(connectionState)}>{getConnectionLabel(connectionState)}</span>
              <span className="badge badge-blue">{activeCount} running now</span>
              <span className={pausedCount > 0 ? "badge badge-red" : "badge badge-green"}>
                {pausedCount} paused
              </span>
              <span className={attentionAgents.length > 0 ? "badge badge-yellow" : "badge badge-green"}>
                {attentionAgents.length} need attention
              </span>
            </div>
          </div>

          <div style={{ display: "grid", gap: "10px", gridTemplateColumns: "repeat(4, minmax(140px, 1fr))", flex: "1 1 520px" }}>
            <div className="card" style={{ padding: "14px" }}>
              <div className="card-label">Discovered 24h</div>
              <div className="card-metric" style={{ marginTop: "6px" }}>
                {overview?.ingestion.discovered_last_24h?.toLocaleString() ?? "—"}
              </div>
            </div>
            <div className="card" style={{ padding: "14px" }}>
              <div className="card-label">Awaiting Triage</div>
              <div className="card-metric" style={{ marginTop: "6px" }}>
                {overview?.triage.pending?.toLocaleString() ?? "—"}
              </div>
            </div>
            <div className="card" style={{ padding: "14px" }}>
              <div className="card-label">Awaiting Analysis</div>
              <div className="card-metric" style={{ marginTop: "6px" }}>
                {overview?.analysis.pending?.toLocaleString() ?? "—"}
              </div>
            </div>
            <div className="card" style={{ padding: "14px" }}>
              <div className="card-label">Analyzed</div>
              <div className="card-metric" style={{ marginTop: "6px" }}>
                {overview?.analysis.completed?.toLocaleString() ?? "—"}
              </div>
            </div>
          </div>
        </section>

        <OperationalAlertsPanel
          agents={sortedAgents.map((entry) => ({
            agent_name: entry.agent_name,
            display_name: entry.display_name,
          }))}
          agentStatuses={sortedAgents}
          failureEvents={failureEvents}
          pauseStates={pauseStates}
          title="Live Operator Alerts"
        />
        <GitHubBudgetPanel snapshot={gatewayRuntimeQuery.data?.runtime.github_api_budget} title="Live GitHub API Budget" />
        <GeminiKeyPoolPanel snapshot={gatewayRuntimeQuery.data?.runtime.gemini_api_key_pool} title="Live Gemini Analyst Key Pool" />
        <AcceptedAnalysisQueuePanel
          pendingCount={overview?.analysis.pending ?? 0}
          title="Accepted Queue Waiting For Analyst"
        />

        <div style={{ display: "grid", gap: "16px", gridTemplateColumns: "minmax(0, 1.7fr) minmax(320px, 1fr)", alignItems: "start" }}>
          <div style={{ minWidth: 0 }}>
            <div className="section-head">
              <span className="section-title">Needs Attention</span>
              <span className="section-line" />
            </div>

            {loading ? (
              <div className="card">Loading live fleet status…</div>
            ) : attentionAgents.length === 0 ? (
              <div className="card">Nothing is currently blocked or demanding operator attention.</div>
            ) : (
              <div style={{ display: "grid", gap: "12px" }}>
                {attentionAgents.map((entry) => (
                  <AgentLiveCard
                    key={entry.agent_name}
                    entry={entry}
                    pauseState={pauseMap.get(entry.agent_name)}
                    failureEvent={latestFailureByAgent.get(entry.agent_name)}
                    runtimeAgent={gatewayAgentMap.get(entry.agent_name)}
                  />
                ))}
              </div>
            )}

            <div className="section-head">
              <span className="section-title">Running Now</span>
              <span className="section-line" />
            </div>

            {runningAgents.length === 0 ? (
              <div className="card">No agents are actively processing work right this second.</div>
            ) : (
              <div style={{ display: "grid", gap: "12px" }}>
                {runningAgents.map((entry) => (
                  <AgentLiveCard
                    key={entry.agent_name}
                    entry={entry}
                    pauseState={pauseMap.get(entry.agent_name)}
                    failureEvent={latestFailureByAgent.get(entry.agent_name)}
                    runtimeAgent={gatewayAgentMap.get(entry.agent_name)}
                  />
                ))}
              </div>
            )}

            <div className="section-head">
              <span className="section-title">Ready Or Idle</span>
              <span className="section-line" />
            </div>

            <div className="card" style={{ padding: "0" }}>
              <div style={{ display: "grid", gap: "1px", background: "var(--border)" }}>
                {readyAgents.length === 0 ? (
                  <div style={{ padding: "16px", background: "var(--bg-2)", color: "var(--text-2)" }}>
                    No agents are currently sitting in a healthy idle state.
                  </div>
                ) : (
                  readyAgents.map((entry) => {
                    const pauseState = pauseMap.get(entry.agent_name);
                    const liveBadge = getAgentLiveBadge(entry, pauseState);
                    return (
                      <div
                        key={entry.agent_name}
                        style={{
                          padding: "12px 14px",
                          background: "var(--bg-2)",
                          display: "grid",
                          gap: "8px",
                          gridTemplateColumns: "minmax(160px, 220px) minmax(0, 1fr) auto",
                          alignItems: "center",
                        }}
                      >
                        <div>
                          <div style={{ color: "var(--text-0)", fontWeight: 600 }}>
                            {formatAgentName(entry.agent_name)}
                          </div>
                          <div style={{ color: "var(--text-2)", fontSize: "12px" }}>{entry.role_label}</div>
                        </div>
                        <div style={{ color: "var(--text-1)" }}>
                          {formatRuntimeProgressHeadline(entry.runtime_progress) || formatItemsSummary(entry.latest_run)}
                        </div>
                        <span className={liveBadge.className}>{liveBadge.label}</span>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>

          <div style={{ minWidth: 0 }}>
            <div className="section-head">
              <span className="section-title">Operator Guidance</span>
              <span className="section-line" />
            </div>

            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">What Should Happen Next</div>
                  <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
                    Suggested next moves based on current queue pressure and failures.
                  </div>
                </div>
              </div>
              <div style={{ display: "grid", gap: "8px" }}>
                {nextActions.length === 0 ? (
                  <div style={{ color: "var(--text-2)" }}>
                    No urgent operator action detected right now.
                  </div>
                ) : (
                  nextActions.map((action) => (
                    <div
                      key={action}
                      style={{
                        borderRadius: "8px",
                        padding: "10px",
                        background: "var(--bg-3)",
                        color: "var(--text-1)",
                      }}
                    >
                      {action}
                    </div>
                  ))
                )}
              </div>
              <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "12px" }}>
                <Link className="btn btn-sm" href="/control">Open Control</Link>
                <Link className="btn btn-sm" href="/repositories">Review Repositories</Link>
                <Link className="btn btn-sm" href="/ideas">Open Ideas</Link>
              </div>
            </div>

            <div className="card" style={{ marginTop: "16px" }}>
              <div className="card-header">
                <div>
                  <div className="card-title">Queue Pressure</div>
                  <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
                    High-level bottlenecks across discovery, triage, and analysis.
                  </div>
                </div>
              </div>
              <div style={{ display: "grid", gap: "10px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                  <span className="card-label">Intake Pending</span>
                  <span style={{ color: "var(--text-0)" }}>
                    {overview?.ingestion.pending_intake?.toLocaleString() ?? "—"}
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                  <span className="card-label">Triage Pending</span>
                  <span style={{ color: "var(--text-0)" }}>
                    {overview?.triage.pending?.toLocaleString() ?? "—"}
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                  <span className="card-label">Analysis Pending</span>
                  <span style={{ color: "var(--text-0)" }}>
                    {overview?.analysis.pending?.toLocaleString() ?? "—"}
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                  <span className="card-label">Analysis Failed</span>
                  <span style={{ color: "var(--text-0)" }}>
                    {overview?.analysis.failed?.toLocaleString() ?? "—"}
                  </span>
                </div>
              </div>
            </div>

            <div className="card" style={{ marginTop: "16px" }}>
              <div className="card-header">
                <div>
                  <div className="card-title">Strategic Blind Spots</div>
                  <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
                    Important product gaps that still affect your end goal.
                  </div>
                </div>
              </div>
              <ul style={{ display: "grid", gap: "8px", paddingLeft: "16px", color: "var(--text-1)" }}>
                {blindSpots.map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        <div className="section-head">
          <span className="section-title">Live Event Feed</span>
          <span className="section-line" />
        </div>

        <EventTimeline events={systemEvents} isLoading={eventsQuery.isLoading} />
      </div>
    </>
  );
}

"use client";

import type {
  AgentPauseState,
  AgentStatusEntry,
  FailureEventPayload,
} from "@/api/agents";
import { formatAppDateTime } from "@/lib/time";

import {
  formatAgentRunStatus,
  formatItemsSummary,
  formatRelativeTimestamp,
  formatRuntimeProgressCounts,
  formatRuntimeProgressHeadline,
} from "./agentPresentation";

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

function formatEstimatedRetryTimestamp(event: FailureEventPayload): string | null {
  if (event.retry_after_seconds == null || event.retry_after_seconds <= 0) {
    return null;
  }
  const createdAt = Date.parse(event.created_at);
  if (Number.isNaN(createdAt)) {
    return null;
  }
  const retryAt = new Date(createdAt + event.retry_after_seconds * 1000);
  return formatAppDateTime(retryAt);
}

function buildCurrentState(
  entry: AgentStatusEntry,
  pauseState: AgentPauseState | undefined,
  failureEvent: FailureEventPayload | undefined,
): string {
  if (pauseState?.is_paused) {
    if (failureEvent?.failure_classification === "rate_limited" && failureEvent.upstream_provider === "github") {
      return "Paused now because GitHub temporarily blocked requests. No work is being processed.";
    }
    if (failureEvent?.failure_classification === "rate_limited" && failureEvent.upstream_provider !== "github") {
      return "Paused now because the model provider throttled requests. No work is being processed.";
    }
    return "Paused now. No work is being processed until the agent is resumed.";
  }

  if (entry.latest_run?.status === "running") {
    return "Actively processing work right now.";
  }

  if (entry.runtime_progress?.current_activity) {
    return "Not processing work right now. Waiting for the next eligible checkpoint or backlog item.";
  }

  return "Idle right now.";
}

function buildLastRunOutcome(entry: AgentStatusEntry): string {
  if (!entry.latest_run) {
    return "No captured run yet.";
  }
  if (entry.latest_run.status === "completed") {
    return `Last run completed successfully: ${formatItemsSummary(entry.latest_run)}.`;
  }
  if (entry.latest_run.status === "running") {
    return `Current run is still active: ${formatItemsSummary(entry.latest_run)}.`;
  }
  if (entry.latest_run.status === "skipped_paused") {
    return "Latest attempted run did not start because the agent was already paused.";
  }
  if (entry.latest_run.status === "skipped") {
    return "Latest run was skipped and did not process work.";
  }
  if (entry.latest_run.status === "failed") {
    return `Latest run failed: ${formatItemsSummary(entry.latest_run)}.`;
  }
  return `Latest run status: ${formatAgentRunStatus(entry.latest_run.status)}.`;
}

function buildWhyThisLooksThisWay(
  entry: AgentStatusEntry,
  pauseState: AgentPauseState | undefined,
): string {
  const progressCounts = formatRuntimeProgressCounts(entry.runtime_progress);

  if (pauseState?.is_paused && entry.latest_run?.status === "completed") {
    return `${progressCounts} describes the next blocked checkpoint, not the earlier successful run. The last run finished, and the agent paused afterward before starting the next one.`;
  }

  if (pauseState?.is_paused && entry.latest_run?.status === "skipped_paused") {
    return `${progressCounts} describes where the agent would resume after unpausing it. The latest run did not process work because pause blocked it.`;
  }

  if (!pauseState?.is_paused && entry.latest_run?.status === "completed") {
    return `${progressCounts} describes the next waiting checkpoint, not active processing.`;
  }

  return `${progressCounts} is the best live checkpoint snapshot currently available.`;
}

function buildRecommendedAction(
  entry: AgentStatusEntry,
  pauseState: AgentPauseState | undefined,
  failureEvent: FailureEventPayload | undefined,
): string {
  if (pauseState?.is_paused) {
    if (failureEvent?.failure_classification === "rate_limited" && failureEvent.upstream_provider === "github") {
      const exactRetry = formatEstimatedRetryTimestamp(failureEvent);
      if (exactRetry) {
        return `Wait until about ${exactRetry}, then resume this agent manually from Control.`;
      }
      return "GitHub did not send an exact retry time. Wait a bit longer, then do one manual resume from Control.";
    }
    if (entry.agent_name === "analyst") {
      return "Open Incidents to inspect the blocking Analyst failure, then resume Analyst manually from Control.";
    }
    return "Review the pause reason, then resume this agent manually from Control.";
  }

  if (entry.latest_run?.status === "running") {
    return "No operator action needed right now. Watch progress and intervene only if an alert appears.";
  }

  if (entry.agent_name === "bouncer") {
    return "No action needed unless new repositories enter triage.";
  }

  return "No immediate action needed. The agent is waiting for the next eligible workload.";
}

function buildRetryGuidance(failureEvent: FailureEventPayload | undefined): string | null {
  if (!failureEvent || failureEvent.failure_classification !== "rate_limited") {
    return null;
  }
  const exactRetry = formatEstimatedRetryTimestamp(failureEvent);
  if (exactRetry) {
    return `Retry window: about ${exactRetry} (${formatRetryWindow(failureEvent.retry_after_seconds)} from the event).`;
  }
  if (failureEvent.upstream_provider === "github") {
    return "Retry window: GitHub did not send an exact reset time. Safe operator approach is to wait around 15 minutes from the alert before one manual retry.";
  }
  return `Retry window: wait ${formatRetryWindow(failureEvent.retry_after_seconds)} before retrying.`;
}

export function AgentOperatorSummary({
  entry,
  pauseState,
  failureEvent,
  title = "Operator Summary",
}: {
  entry: AgentStatusEntry | null | undefined;
  pauseState?: AgentPauseState;
  failureEvent?: FailureEventPayload;
  title?: string;
}) {
  if (!entry) {
    return (
      <section className="card">
        <div className="card-header">
          <div className="card-title">{title}</div>
        </div>
        <div style={{ color: "var(--text-2)" }}>Loading operator summary…</div>
      </section>
    );
  }

  const currentState = buildCurrentState(entry, pauseState, failureEvent);
  const lastRunOutcome = buildLastRunOutcome(entry);
  const whyThisLooksThisWay = buildWhyThisLooksThisWay(entry, pauseState);
  const recommendedAction = buildRecommendedAction(entry, pauseState, failureEvent);
  const retryGuidance = buildRetryGuidance(failureEvent);

  return (
    <section className="card">
      <div className="card-header">
        <div>
          <div className="card-title">{title}</div>
          <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
            Plain-language explanation of what is happening now and what to do next.
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gap: "12px" }}>
        <div style={{ display: "grid", gap: "10px", gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
            <div className="card-label">Current State</div>
            <div style={{ color: "var(--text-0)", marginTop: "6px", lineHeight: 1.6 }}>{currentState}</div>
          </div>
          <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
            <div className="card-label">Last Run Outcome</div>
            <div style={{ color: "var(--text-0)", marginTop: "6px", lineHeight: 1.6 }}>{lastRunOutcome}</div>
          </div>
        </div>

        <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
          <div className="card-label">What It Would Do Next</div>
          <div style={{ color: "var(--text-0)", marginTop: "6px" }}>
            {formatRuntimeProgressHeadline(entry.runtime_progress)}
          </div>
          <div style={{ color: "var(--text-2)", marginTop: "6px", lineHeight: 1.6 }}>
            {whyThisLooksThisWay}
          </div>
          <div style={{ color: "var(--text-2)", marginTop: "6px", fontSize: "12px" }}>
            Current target: {entry.runtime_progress?.current_target ?? "No active target"}
          </div>
          <div style={{ color: "var(--text-2)", marginTop: "4px", fontSize: "12px" }}>
            Last runtime update: {entry.runtime_progress?.updated_at ? formatRelativeTimestamp(entry.runtime_progress.updated_at) : "Unavailable"}
          </div>
        </div>

        {failureEvent ? (
          <div style={{ background: "var(--yellow-dim)", border: "1px solid rgba(217, 166, 58, 0.3)", borderRadius: "8px", padding: "12px" }}>
            <div className="card-label" style={{ color: "var(--yellow)" }}>Latest Alert</div>
            <div style={{ color: "var(--text-0)", marginTop: "6px", lineHeight: 1.6 }}>
              {failureEvent.message}
            </div>
            {retryGuidance ? (
              <div style={{ color: "var(--text-1)", marginTop: "6px", lineHeight: 1.6 }}>
                {retryGuidance}
              </div>
            ) : null}
          </div>
        ) : null}

        {pauseState?.is_paused ? (
          <div style={{ background: "var(--red-dim)", border: "1px solid rgba(217, 79, 79, 0.3)", borderRadius: "8px", padding: "12px" }}>
            <div className="card-label" style={{ color: "var(--red)" }}>Pause Reason</div>
            <div style={{ color: "var(--text-0)", marginTop: "6px", lineHeight: 1.6 }}>
              {pauseState.pause_reason ?? "Pause active, but no reason was recorded."}
            </div>
            <div style={{ color: "var(--text-2)", marginTop: "6px", fontSize: "12px" }}>
              Paused {pauseState.paused_at ? formatRelativeTimestamp(pauseState.paused_at) : "recently"}
            </div>
          </div>
        ) : null}

        <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
          <div className="card-label">Recommended Action</div>
          <div style={{ color: "var(--text-0)", marginTop: "6px", lineHeight: 1.6 }}>
            {recommendedAction}
          </div>
        </div>
      </div>
    </section>
  );
}

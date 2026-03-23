"use client";

import Link from "next/link";

import type {
  AgentPauseState,
  AgentStatusEntry,
  FailureEventPayload,
} from "@/api/agents";
import { formatAppDateTime } from "@/lib/time";
import { formatAgentName, formatRelativeTimestamp } from "./agentPresentation";
import { isFailureStillActive } from "./alertState";

function formatRetryAfter(seconds: number | null): string {
  if (seconds == null || seconds <= 0) {
    return "Retry window unavailable (provider did not send one)";
  }
  if (seconds < 60) {
    return `Retry after ${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return remainingSeconds > 0
    ? `Retry after ${minutes}m ${remainingSeconds}s`
    : `Retry after ${minutes}m`;
}

function dedupeByAgent<T extends { agent_name: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.agent_name)) {
      return false;
    }
    seen.add(item.agent_name);
    return true;
  });
}

function formatRetryTimestamp(event: FailureEventPayload): string | null {
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

function formatRateLimitTitle(event: FailureEventPayload, label: string): string {
  if (event.upstream_provider === "github") {
    return `GitHub rate limit hit in ${label}`;
  }
  if (event.upstream_provider === "llm") {
    return `Model provider rate limit hit in ${label}`;
  }
  return `Rate limit hit in ${label}`;
}

function buildRateLimitGuidance(
  event: FailureEventPayload,
  pausedState: AgentPauseState | undefined,
  label: string,
): string {
  const retryWindow = formatRetryAfter(event.retry_after_seconds);
  const retryAt = formatRetryTimestamp(event);
  const seenLabel = `Seen ${formatRelativeTimestamp(event.created_at)}.`;
  const retryDetail = retryAt ? `${retryWindow}. Safe retry time is about ${retryAt}.` : retryWindow;

  if (event.agent_name === "analyst" && event.upstream_provider === "github") {
    if (pausedState?.is_paused) {
      return `${retryDetail} ${seenLabel} ${label} also appears to be paused for a separate reason: ${pausedState.pause_reason ?? "policy pause active"}. GitHub rate limits do not auto-resume Analyst; after cooldown, rerun Analyst manually.`;
    }
    if (!retryAt && event.upstream_provider === "github") {
      return `${retryWindow}. ${seenLabel} GitHub did not send an exact reset time. Safe operator estimate: wait about 15 minutes from the alert, then rerun Analyst manually once.`;
    }
    return `${retryDetail} ${seenLabel} Analyst stops the current run early, leaves remaining repositories pending, and should be run again manually after cooldown.`;
  }

  if (pausedState?.is_paused) {
    if (!retryAt && event.upstream_provider === "github") {
      return `${retryWindow}. ${seenLabel} ${label} is currently paused: ${pausedState.pause_reason ?? "policy pause active"}. GitHub did not send an exact reset time, so the safe operator estimate is to wait about 15 minutes from the alert before one manual resume.`;
    }
    return `${retryDetail} ${seenLabel} ${label} is currently paused: ${pausedState.pause_reason ?? "policy pause active"}. Resume it manually after the rate-limit window clears.`;
  }

  if (!retryAt && event.upstream_provider === "github") {
    return `${retryWindow}. ${seenLabel} GitHub did not send an exact reset time. Safe operator estimate: wait about 15 minutes from the alert before one manual retry.`;
  }
  return `${retryWindow}. ${seenLabel} If the worker loop does not recover on its own, rerun the agent manually after cooldown.`;
}

export function OperationalAlertsPanel({
  pauseStates,
  failureEvents,
  agents = [],
  agentStatuses = [],
  title = "Operator Alerts",
}: {
  pauseStates: AgentPauseState[];
  failureEvents: FailureEventPayload[];
  agents?: Array<{ agent_name: string; display_name: string }>;
  agentStatuses?: AgentStatusEntry[];
  title?: string;
}) {
  const pauseMap = new Map(pauseStates.map((state) => [state.agent_name, state]));
  const statusMap = new Map(agentStatuses.map((entry) => [entry.agent_name, entry]));
  const rateLimitedAlerts = dedupeByAgent(
    failureEvents.filter(
      (event) =>
        event.failure_classification === "rate_limited" &&
        isFailureStillActive(event, statusMap.get(event.agent_name), pauseMap.get(event.agent_name)),
    ),
  );
  const blockingAlerts = dedupeByAgent(
    failureEvents.filter(
      (event) =>
        event.failure_classification === "blocking" &&
        isFailureStillActive(event, statusMap.get(event.agent_name), pauseMap.get(event.agent_name)),
    ),
  );
  const pausedAgents = pauseStates.filter((state) => state.is_paused);
  const rateLimitedAgentNames = new Set(rateLimitedAlerts.map((event) => event.agent_name));

  if (rateLimitedAlerts.length === 0 && blockingAlerts.length === 0 && pausedAgents.length === 0) {
    return null;
  }

  const agentNameById = new Map(agents.map((agent) => [agent.agent_name, agent.display_name]));

  return (
    <section
      className="card"
      style={{
        marginBottom: "16px",
        borderColor: "var(--amber)",
        background: "color-mix(in srgb, var(--amber-dim) 55%, var(--bg-0))",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "12px",
          marginBottom: "12px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <div className="card-title" style={{ color: "var(--text-0)" }}>
            {title}
          </div>
          <div style={{ fontSize: "12px", color: "var(--text-1)", marginTop: "4px" }}>
            Important runtime issues are active right now.
          </div>
        </div>
        <Link className="btn btn-sm" href="/incidents">
          Open Incidents
        </Link>
      </div>

      <div style={{ display: "grid", gap: "10px" }}>
        {rateLimitedAlerts.map((event) => {
          const pausedState = pauseMap.get(event.agent_name);
          const label = agentNameById.get(event.agent_name) ?? formatAgentName(event.agent_name);
          return (
            <div
              key={`rate-limit-${event.id}`}
              style={{
                padding: "12px",
                borderRadius: "8px",
                border: "1px solid var(--amber)",
                background: "color-mix(in srgb, var(--amber-dim) 70%, var(--bg-0))",
              }}
            >
              <div style={{ fontSize: "13px", fontWeight: 700, color: "var(--text-0)" }}>
                {formatRateLimitTitle(event, label)}
              </div>
              <div style={{ fontSize: "12px", color: "var(--text-1)", marginTop: "6px", lineHeight: 1.6 }}>
                {event.message}
              </div>
              <div style={{ fontSize: "12px", color: "var(--text-1)", marginTop: "8px", lineHeight: 1.6 }}>
                {buildRateLimitGuidance(event, pausedState, label)}
              </div>
            </div>
          );
        })}

        {pausedAgents
          .filter((state) => !rateLimitedAgentNames.has(state.agent_name))
          .map((state) => {
          const label = agentNameById.get(state.agent_name) ?? formatAgentName(state.agent_name);
          return (
            <div
              key={`paused-${state.agent_name}`}
              style={{
                padding: "12px",
                borderRadius: "8px",
                border: "1px solid var(--red)",
                background: "color-mix(in srgb, var(--red-dim) 70%, var(--bg-0))",
              }}
            >
              <div style={{ fontSize: "13px", fontWeight: 700, color: "var(--text-0)" }}>
                {label} is paused
              </div>
              <div style={{ fontSize: "12px", color: "var(--text-1)", marginTop: "6px", lineHeight: 1.6 }}>
                {state.pause_reason ?? "No pause reason was recorded."}
              </div>
              {state.paused_at ? (
                <div style={{ fontSize: "12px", color: "var(--text-2)", marginTop: "8px" }}>
                  Paused {formatRelativeTimestamp(state.paused_at)}
                </div>
              ) : null}
            </div>
          );
        })}

        {blockingAlerts
          .filter((event) => !pauseMap.get(event.agent_name)?.is_paused)
          .map((event) => {
            const label = agentNameById.get(event.agent_name) ?? formatAgentName(event.agent_name);
            return (
              <div
                key={`blocking-${event.id}`}
                style={{
                  padding: "12px",
                  borderRadius: "8px",
                  border: "1px solid var(--red)",
                  background: "color-mix(in srgb, var(--red-dim) 55%, var(--bg-0))",
                }}
              >
                <div style={{ fontSize: "13px", fontWeight: 700, color: "var(--text-0)" }}>
                  Blocking failure in {label}
                </div>
                <div style={{ fontSize: "12px", color: "var(--text-1)", marginTop: "6px", lineHeight: 1.6 }}>
                  {event.message}
                </div>
                <div style={{ fontSize: "12px", color: "var(--text-2)", marginTop: "8px" }}>
                  Seen {formatRelativeTimestamp(event.created_at)}
                </div>
              </div>
            );
          })}
      </div>
    </section>
  );
}

"use client";

import { useState } from "react";
import type { GitHubApiBudgetSnapshot, GeminiApiKeyPoolSnapshot } from "@/lib/gateway-contract";
import type { AgentPauseState, AgentStatusEntry, FailureEventPayload } from "@/api/agents";
import { formatRelativeTimestamp, formatTimestampLabel } from "@/components/agents/agentPresentation";
import { isFailureStillActive } from "@/components/agents/alertState";

function formatBudgetValue(value: number | null): string {
  if (value == null) return "—";
  return value.toLocaleString();
}

function getGitHubDot(snapshot: GitHubApiBudgetSnapshot | null | undefined): "green" | "amber" | "red" | "muted" {
  if (!snapshot) return "muted";
  if (snapshot.exhausted || (snapshot.remaining ?? 1) <= 0) return "red";
  if (snapshot.limit != null && snapshot.remaining != null) {
    const ratio = snapshot.limit > 0 ? snapshot.remaining / snapshot.limit : 0;
    if (ratio <= 0.1 || snapshot.remaining <= 250) return "amber";
  }
  return "green";
}

function getGeminiDot(snapshot: GeminiApiKeyPoolSnapshot | null | undefined): "green" | "amber" | "red" | "muted" {
  if (!snapshot) return "muted";
  const healthy = snapshot.keys.filter((k) => k.status === "healthy").length;
  const errored = snapshot.keys.filter((k) => k.status === "auth-error").length;
  if (errored > 0) return "red";
  if (healthy === 0) return "amber";
  if (healthy < snapshot.keys.length) return "amber";
  return "green";
}

function getAlertDot(
  pauseStates: AgentPauseState[],
  failureEvents: FailureEventPayload[],
  agentStatuses: AgentStatusEntry[],
): "green" | "amber" | "red" | "muted" {
  const paused = pauseStates.filter((s) => s.is_paused).length;
  const pauseMap = new Map(pauseStates.map((s) => [s.agent_name, s]));
  const statusMap = new Map(agentStatuses.map((e) => [e.agent_name, e]));
  const activeFailures = failureEvents.filter(
    (event) => isFailureStillActive(event, statusMap.get(event.agent_name), pauseMap.get(event.agent_name)),
  ).length;
  if (paused > 0) return "red";
  if (activeFailures > 0) return "amber";
  return "green";
}

export function StatusBar({
  githubBudget,
  geminiKeyPool,
  pauseStates,
  failureEvents,
  agentStatuses,
  runningCount,
  readyCount,
  totalAgents,
  queuePending,
  onExpandGitHub,
  onExpandGemini,
}: {
  githubBudget: GitHubApiBudgetSnapshot | null | undefined;
  geminiKeyPool: GeminiApiKeyPoolSnapshot | null | undefined;
  pauseStates: AgentPauseState[];
  failureEvents: FailureEventPayload[];
  agentStatuses: AgentStatusEntry[];
  runningCount: number;
  readyCount: number;
  totalAgents: number;
  queuePending: number;
  onExpandGitHub?: () => void;
  onExpandGemini?: () => void;
}) {
  const ghDot = getGitHubDot(githubBudget);
  const gemDot = getGeminiDot(geminiKeyPool);
  const alertDot = getAlertDot(pauseStates, failureEvents, agentStatuses);
  const pausedCount = pauseStates.filter((s) => s.is_paused).length;
  const healthyGemini = geminiKeyPool?.keys.filter((k) => k.status === "healthy").length ?? 0;
  const totalGemini = geminiKeyPool?.keys.length ?? 0;
  const healthLabel =
    alertDot === "green" ? "All clear" : pausedCount > 0 ? `${pausedCount} paused` : "Needs review";

  return (
    <div className="status-bar">
      <div className="status-card">
        <div className="status-card-label">System</div>
        <div className="status-card-value">
          <span className={`status-dot status-dot-${alertDot} ${alertDot !== "green" ? "status-dot-pulse" : ""}`} />
          <span
            style={{
              color: alertDot === "green" ? "var(--green)" : alertDot === "red" ? "var(--red)" : "var(--amber)",
            }}
          >
            {healthLabel}
          </span>
        </div>
      </div>

      <div className="status-card">
        <div className="status-card-label">Agents</div>
        <div className="status-card-value">
          <span style={{ color: runningCount > 0 ? "var(--amber)" : "var(--text-0)" }}>{runningCount}</span>
          <span style={{ color: "var(--text-3)" }}>/</span>
          <span style={{ color: "var(--text-0)" }}>{totalAgents}</span>
        </div>
        <div className="status-card-meta">{readyCount} idle</div>
      </div>

      <button
        type="button"
        className="status-card status-card-button"
        onClick={onExpandGitHub}
        title="Click to see full GitHub budget"
      >
        <div className="status-card-label">GitHub Budget</div>
        <div className="status-card-value">
          <span className={`status-dot status-dot-${ghDot}`} />
          <span>{formatBudgetValue(githubBudget?.remaining ?? null)}</span>
        </div>
        <div className="status-card-meta">of {formatBudgetValue(githubBudget?.limit ?? null)}</div>
      </button>

      <button
        type="button"
        className="status-card status-card-button"
        onClick={onExpandGemini}
        title="Click to see full Gemini key pool"
      >
        <div className="status-card-label">Gemini Pool</div>
        <div className="status-card-value">
          <span className={`status-dot status-dot-${gemDot}`} />
          <span>
            {healthyGemini}/{totalGemini}
          </span>
        </div>
        <div className="status-card-meta">healthy keys</div>
      </button>

      <div className="status-card">
        <div className="status-card-label">Analysis Queue</div>
        <div className="status-card-value" style={{ color: queuePending > 0 ? "var(--blue)" : "var(--text-0)" }}>
          {queuePending}
        </div>
        <div className="status-card-meta">waiting now</div>
      </div>
    </div>
  );
}

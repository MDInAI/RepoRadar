"use client";

import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchAgentConfig,
  fetchBackfillTimeline,
  fetchAgentPauseStates,
  fetchLatestAgentRuns,
  getAgentConfigQueryKey,
  getBackfillTimelineQueryKey,
  getAgentPauseStatesQueryKey,
  getLatestAgentRunsQueryKey,
  pauseAgent,
  resumeAgent,
  triggerAgentRun,
  updateBackfillTimeline,
  updateAgentConfig,
  type AgentConfigField,
  type AgentConfigResponse,
  type BackfillTimelineResponse,
  type AgentName,
  type AgentStatusEntry,
} from "@/api/agents";
import { fetchGatewayRuntime, fetchSettingsSummary } from "@/api/readiness";
import type {
  GatewayAgentIntakeQueueSummary,
  GatewayAgentQueue,
} from "@/lib/gateway-contract";
import type { MaskedSettingSummary, SettingsSummaryResponse } from "@/lib/settings-contract";

type AgentDefinition = {
  id: AgentName;
  label: string;
  icon: string;
  fallbackDescription: string;
};

const AGENTS: AgentDefinition[] = [
  { id: "overlord", label: "Overlord", icon: "👑", fallbackDescription: "Control-plane placeholder" },
  { id: "firehose", label: "Firehose", icon: "🔥", fallbackDescription: "Real-time discovery" },
  { id: "backfill", label: "Backfill", icon: "⏮️", fallbackDescription: "Historical discovery" },
  { id: "bouncer", label: "Bouncer", icon: "🚪", fallbackDescription: "Rule-based triage" },
  { id: "analyst", label: "Analyst", icon: "🔬", fallbackDescription: "README analysis" },
  { id: "combiner", label: "Combiner", icon: "🧠", fallbackDescription: "Opportunity synthesis" },
  { id: "obsession", label: "Obsession", icon: "🗂️", fallbackDescription: "Context tracking" },
];

const EDITABLE_AGENT_IDS: AgentName[] = ["firehose", "backfill", "bouncer"];

function isLiveIntakeQueue(queue: GatewayAgentQueue): queue is GatewayAgentIntakeQueueSummary {
  return queue.status === "live";
}

function titleCase(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown";
  }
  return `${parsed.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function formatRelative(value: string | null | undefined): string {
  if (!value) {
    return "Never";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown";
  }
  const diffMs = Date.now() - parsed.getTime();
  const diffMinutes = Math.round(diffMs / 60000);
  if (diffMinutes < 1) {
    return "Just now";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  const diffDays = Math.round(diffHours / 24);
  return `${diffDays}d ago`;
}

function formatTokens(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return value.toLocaleString();
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) {
    return "Unavailable";
  }
  const rounded = Math.max(0, Math.round(seconds));
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const secs = rounded % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
}

function toValidTimestamp(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? null : parsed;
}

function formatTimeUntilScheduledRun(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown";
  }
  const diffSeconds = Math.round((parsed.getTime() - Date.now()) / 1000);
  if (diffSeconds > 0) {
    return `In ${formatDuration(diffSeconds)}`;
  }
  if (diffSeconds === 0) {
    return "Due now";
  }
  return `Overdue by ${formatDuration(Math.abs(diffSeconds))}`;
}

function formatEvidenceTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }
  return `${formatRelative(value)} (${formatTimestamp(value)})`;
}

function subtractOneDay(dateValue: string | null | undefined): string | null {
  if (!dateValue) {
    return null;
  }
  const parsed = new Date(`${dateValue}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  parsed.setUTCDate(parsed.getUTCDate() - 1);
  return parsed.toISOString().slice(0, 10);
}

function findSettingValue(
  summary: SettingsSummaryResponse | undefined,
  keys: readonly string[],
): string | null {
  if (!summary) {
    return null;
  }
  for (const key of keys) {
    const workerSetting = summary.worker_settings.find((entry) => entry.key === key);
    if (workerSetting?.value) {
      return workerSetting.value;
    }
    const projectSetting = summary.project_settings.find((entry) => entry.key === key);
    if (projectSetting?.value) {
      return projectSetting.value;
    }
  }
  return null;
}

function findNumericSetting(
  summary: SettingsSummaryResponse | undefined,
  keys: readonly string[],
): number | null {
  const value = findSettingValue(summary, keys);
  if (value == null) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function findSettingEntry(
  summary: SettingsSummaryResponse | undefined,
  keys: readonly string[],
): MaskedSettingSummary | null {
  if (!summary) {
    return null;
  }
  for (const key of keys) {
    const workerSetting = summary.worker_settings.find((entry) => entry.key === key);
    if (workerSetting) {
      return workerSetting;
    }
    const projectSetting = summary.project_settings.find((entry) => entry.key === key);
    if (projectSetting) {
      return projectSetting;
    }
  }
  return null;
}

type AgentCadence = {
  mode: "interval" | "queue" | "manual";
  stateLabel: string;
  explanation: string;
  intervalSeconds: number | null;
  remainingSeconds: number | null;
  nextDueAt: string | null;
  lastCheckpointAt: string | null;
  progressRatio: number | null;
  actionLabel: string;
  actionAvailable: boolean;
  actionReason: string | null;
  schedulerStatusLabel: string;
  schedulerStatusTone: "default" | "good" | "warn";
  schedulerStatusExplanation: string;
  lastSchedulerEvidenceAt: string | null;
};

function deriveCadenceForAgent({
  agentId,
  isPaused,
  pauseReason,
  runtimeQueue,
  latestRun,
  settingsSummary,
}: {
  agentId: AgentName;
  isPaused: boolean;
  pauseReason: string | null | undefined;
  runtimeQueue: GatewayAgentIntakeQueueSummary | null;
  latestRun: AgentStatusEntry["latest_run"] | null | undefined;
  settingsSummary: SettingsSummaryResponse | undefined;
}): AgentCadence {
  const nowMs = Date.now();
  const lastCheckpointAt =
    runtimeQueue?.checkpoint.last_checkpointed_at ?? latestRun?.completed_at ?? latestRun?.started_at ?? null;
  const evidenceCandidates = [
    runtimeQueue?.checkpoint.last_checkpointed_at ?? null,
    runtimeQueue?.checkpoint.kind === "firehose" ? runtimeQueue.checkpoint.run_started_at : null,
    latestRun?.completed_at ?? null,
    latestRun?.started_at ?? null,
  ];
  const lastSchedulerEvidenceAt =
    evidenceCandidates
      .map((value) => ({ value, parsed: toValidTimestamp(value) }))
      .filter((entry): entry is { value: string; parsed: number } => entry.parsed != null && entry.value != null)
      .sort((left, right) => right.parsed - left.parsed)[0]?.value ?? null;

  if (agentId === "firehose" || agentId === "backfill") {
    const intervalSeconds = findNumericSetting(settingsSummary, [
      agentId === "firehose" ? "workers.FIREHOSE_INTERVAL_SECONDS" : "workers.BACKFILL_INTERVAL_SECONDS",
      agentId === "firehose" ? "FIREHOSE_INTERVAL_SECONDS" : "BACKFILL_INTERVAL_SECONDS",
    ]);

    const checkpointTimeMs = lastCheckpointAt ? new Date(lastCheckpointAt).getTime() : null;
    const canResumeImmediately =
      runtimeQueue != null &&
      "resume_required" in runtimeQueue.checkpoint &&
      Boolean(runtimeQueue.checkpoint.resume_required);

    let remainingSeconds: number | null = null;
    let progressRatio: number | null = null;
    let nextDueAt: string | null = null;

    if (intervalSeconds != null) {
      if (canResumeImmediately || checkpointTimeMs == null || Number.isNaN(checkpointTimeMs)) {
        remainingSeconds = 0;
      } else {
        const elapsedSeconds = Math.max(0, (nowMs - checkpointTimeMs) / 1000);
        remainingSeconds = Math.max(0, intervalSeconds - elapsedSeconds);
        progressRatio = Math.max(0, Math.min(1, elapsedSeconds / intervalSeconds));
        nextDueAt = new Date(checkpointTimeMs + intervalSeconds * 1000).toISOString();
      }
    }

    if (isPaused) {
      return {
        mode: "interval",
        stateLabel: "Paused by policy",
        explanation: pauseReason ?? "This cadence is blocked until an operator resumes the agent.",
        intervalSeconds,
        remainingSeconds,
        nextDueAt,
        lastCheckpointAt,
        progressRatio,
        actionLabel: "Run Now",
        actionAvailable: false,
        actionReason: "Resume the agent first to allow manual runs.",
        schedulerStatusLabel: "Paused",
        schedulerStatusTone: "warn",
        schedulerStatusExplanation:
          "Automatic runs are blocked while this agent is paused, even if the scheduled time has already passed.",
        lastSchedulerEvidenceAt,
      };
    }

    if (canResumeImmediately) {
      return {
        mode: "interval",
        stateLabel: "Ready to resume",
        explanation: "The checkpoint requests an immediate resume on the next eligible cycle.",
        intervalSeconds,
        remainingSeconds: 0,
        nextDueAt: lastCheckpointAt,
        lastCheckpointAt,
        progressRatio: 1,
        actionLabel: "Run Now",
        actionAvailable: true,
        actionReason: null,
        schedulerStatusLabel: "Resume requested",
        schedulerStatusTone: "good",
        schedulerStatusExplanation:
          "The checkpoint is asking for an immediate resume. It should start as soon as the scheduler loop picks it up or if you run it manually now.",
        lastSchedulerEvidenceAt,
      };
    }

    if (intervalSeconds == null) {
      return {
        mode: "interval",
        stateLabel: "Cadence unavailable",
        explanation: "The control panel could not resolve the current worker interval settings.",
        intervalSeconds: null,
        remainingSeconds: null,
        nextDueAt: null,
        lastCheckpointAt,
        progressRatio: null,
        actionLabel: "Run Now",
        actionAvailable: false,
        actionReason: "The control panel could not resolve the current worker interval settings.",
        schedulerStatusLabel: "Unavailable",
        schedulerStatusTone: "warn",
        schedulerStatusExplanation:
          "The control panel could not resolve the worker cadence, so it cannot infer whether auto-run scheduling is healthy.",
        lastSchedulerEvidenceAt,
      };
    }

    if ((remainingSeconds ?? 0) <= 0) {
      const overdueSeconds = nextDueAt ? Math.max(0, Math.round((Date.now() - new Date(nextDueAt).getTime()) / 1000)) : 0;
      let schedulerStatusLabel = "Due now";
      let schedulerStatusTone: "default" | "good" | "warn" = "good";
      let schedulerStatusExplanation =
        "The scheduled time has arrived. This agent should start by itself on the next scheduler tick if the worker loop is alive.";

      if (overdueSeconds > 0 && overdueSeconds <= 300) {
        schedulerStatusLabel = "Awaiting scheduler pickup";
        schedulerStatusTone = "default";
        schedulerStatusExplanation =
          "The scheduled time has just passed. This usually means the agent is eligible and waiting for the next scheduler pass, or you can run it manually now.";
      } else if (overdueSeconds > 300 && overdueSeconds <= intervalSeconds) {
        schedulerStatusLabel = "Overdue";
        schedulerStatusTone = "warn";
        schedulerStatusExplanation =
          "The scheduled time passed a while ago and the agent still has not started. It is eligible to auto-run, but the scheduler loop may not be actively picking up jobs right now.";
      } else if (overdueSeconds > intervalSeconds) {
        schedulerStatusLabel = "Scheduler may be offline";
        schedulerStatusTone = "warn";
        schedulerStatusExplanation =
          "This run is overdue by more than one full interval. That usually means the scheduler loop is not currently active, because overdue alone should not keep the agent waiting this long.";
      }

      return {
        mode: "interval",
        stateLabel: "Ready now",
        explanation: `The ${agentId} cadence has cooled down and can start on the next scheduler opportunity.`,
        intervalSeconds,
        remainingSeconds: 0,
        nextDueAt,
        lastCheckpointAt,
        progressRatio: 1,
        actionLabel: "Run Now",
        actionAvailable: true,
        actionReason: null,
        schedulerStatusLabel,
        schedulerStatusTone,
        schedulerStatusExplanation,
        lastSchedulerEvidenceAt,
      };
    }

    return {
      mode: "interval",
      stateLabel: "Waiting on interval",
      explanation: `This agent is idle until its configured ${formatDuration(intervalSeconds)} cadence finishes cooling down.`,
      intervalSeconds,
      remainingSeconds,
      nextDueAt,
      lastCheckpointAt,
      progressRatio,
      actionLabel: "Run Now",
      actionAvailable: true,
      actionReason: null,
      schedulerStatusLabel: "On schedule",
      schedulerStatusTone: "good",
      schedulerStatusExplanation:
        "The cadence is still cooling down. This agent is not expected to start again until the scheduled time arrives.",
      lastSchedulerEvidenceAt,
    };
  }

  if (agentId === "bouncer") {
    return {
      mode: "queue",
      stateLabel: isPaused ? "Paused by policy" : "Queue-driven",
      explanation: isPaused
        ? (pauseReason ?? "Bouncer is paused until an operator resumes it.")
        : "Bouncer runs when pending repositories need triage.",
      intervalSeconds: null,
      remainingSeconds: null,
      nextDueAt: null,
      lastCheckpointAt,
      progressRatio: null,
      actionLabel: "Run Now",
      actionAvailable: !isPaused,
      actionReason: isPaused ? "Resume the agent first to allow manual runs." : null,
      schedulerStatusLabel: isPaused ? "Paused" : "Queue-driven",
      schedulerStatusTone: isPaused ? "warn" : "default",
      schedulerStatusExplanation: isPaused
        ? "Automatic queue pickup is blocked while this agent is paused."
        : "This agent does not wait for a clock time. It runs whenever queue work is available and the worker loop is active.",
      lastSchedulerEvidenceAt,
    };
  }

  if (agentId === "analyst") {
    return {
      mode: "queue",
      stateLabel: isPaused ? "Paused by policy" : "Queue-driven",
      explanation: isPaused
        ? (pauseReason ?? "Analyst is paused until an operator resumes it.")
        : "Analyst runs when accepted repositories are waiting for README analysis.",
      intervalSeconds: null,
      remainingSeconds: null,
      nextDueAt: null,
      lastCheckpointAt,
      progressRatio: null,
      actionLabel: isPaused ? "Resume Analyst" : "Run Now",
      actionAvailable: !isPaused,
      actionReason: isPaused ? "Resume Analyst to clear the policy pause." : null,
      schedulerStatusLabel: isPaused ? "Paused" : "Queue-driven",
      schedulerStatusTone: isPaused ? "warn" : "default",
      schedulerStatusExplanation: isPaused
        ? "Automatic analysis is blocked while this policy pause is in effect."
        : "This agent does not wait for a clock time. It runs when accepted repositories are waiting and the worker loop is active.",
      lastSchedulerEvidenceAt,
    };
  }

  return {
    mode: "manual",
    stateLabel: "Manual / on-demand",
    explanation:
      agentId === "combiner"
        ? "Combiner is triggered from repository and ideas workflows, not on a recurring cadence."
        : agentId === "obsession"
          ? "Obsession refreshes are initiated from context workflows, not on a recurring cadence."
          : "This agent is not currently operating on a recurring worker cycle.",
    intervalSeconds: null,
    remainingSeconds: null,
    nextDueAt: null,
    lastCheckpointAt,
    progressRatio: null,
    actionLabel: "No cycle",
    actionAvailable: false,
    actionReason: "This agent does not currently expose a recurring run loop from the control panel.",
    schedulerStatusLabel: "Manual trigger only",
    schedulerStatusTone: "default",
    schedulerStatusExplanation:
      "This agent does not currently advertise a recurring scheduler loop on this control surface.",
    lastSchedulerEvidenceAt,
  };
}

function AgentBtn({
  agent,
  active,
  paused,
  onClick,
}: {
  agent: AgentDefinition;
  active: boolean;
  paused: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        width: "100%",
        padding: "12px",
        background: active ? "var(--amber-dim)" : "transparent",
        color: active ? "var(--amber)" : "var(--text-2)",
        border: "none",
        borderRadius: "6px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        cursor: "pointer",
        marginBottom: "4px",
        fontSize: "13px",
        fontWeight: 500,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <span>{agent.icon}</span>
        <span>{agent.label}</span>
      </div>
      {paused ? <span style={{ fontSize: "10px", color: "var(--red)" }}>●</span> : null}
    </button>
  );
}

function ConfigPanel({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className="card" style={{ marginBottom: "16px" }}>
      {title ? (
        <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-0)", marginBottom: "12px" }}>
          {title}
        </div>
      ) : null}
      {children}
    </div>
  );
}

function DetailRow({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  tone?: "default" | "good" | "warn";
}) {
  const color =
    tone === "good" ? "var(--green)" : tone === "warn" ? "var(--amber)" : "var(--text-0)";

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        gap: "16px",
        padding: "8px 0",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <span style={{ fontSize: "12px", color: "var(--text-2)" }}>{label}</span>
      <span style={{ fontSize: "12px", color, fontFamily: "var(--mono)", textAlign: "right" }}>
        {value}
      </span>
    </div>
  );
}

function LatestRunPanel({ entry }: { entry: AgentStatusEntry | undefined }) {
  if (!entry) {
    return null;
  }

  return (
    <ConfigPanel title="Last Run Metrics">
      <DetailRow
        label="Run status"
        value={
          entry.latest_run?.started_at
            ? `${titleCase(entry.latest_run.status)} · ${formatRelative(entry.latest_run.started_at)}`
            : "Never"
        }
        tone={
          entry.latest_run?.status === "failed"
            ? "warn"
            : entry.latest_run?.status === "completed"
              ? "good"
              : "default"
        }
      />
      <DetailRow
        label="Items processed"
        value={entry.latest_run?.items_processed?.toLocaleString() ?? "Unavailable"}
      />
      {entry.latest_intake_summary ? (
        <>
          <DetailRow
            label="Fetched from source"
            value={entry.latest_intake_summary.fetched.toLocaleString()}
          />
          <DetailRow
            label="Inserted new"
            value={entry.latest_intake_summary.inserted.toLocaleString()}
            tone="good"
          />
          <DetailRow
            label="Skipped existing"
            value={entry.latest_intake_summary.skipped.toLocaleString()}
          />
          <DetailRow
            label="Reason for skipped"
            value={
              entry.latest_intake_summary.skipped > 0
                ? `${entry.latest_intake_summary.duplicates.toLocaleString()} duplicates / already-known repos`
                : "No skipped intake items"
            }
          />
        </>
      ) : null}
      <DetailRow
        label="Succeeded"
        value={entry.latest_run?.items_succeeded?.toLocaleString() ?? "Unavailable"}
        tone="good"
      />
      <DetailRow
        label="Failed"
        value={entry.latest_run?.items_failed?.toLocaleString() ?? "Unavailable"}
        tone={entry.latest_run?.items_failed ? "warn" : "default"}
      />
      <DetailRow
        label="Duration"
        value={formatDuration(entry.latest_run?.duration_seconds)}
      />
      <DetailRow label="Provider" value={entry.latest_run?.provider_name ?? entry.configured_provider ?? "None"} />
      <DetailRow label="Model" value={entry.latest_run?.model_name ?? entry.configured_model ?? "None"} />
      <DetailRow
        label="Tokens"
        value={
          entry.latest_run?.total_tokens != null
            ? formatTokens(entry.latest_run.total_tokens)
            : "0"
        }
      />
      <DetailRow
        label="Error"
        value={entry.latest_run?.error_summary ?? "No error recorded"}
        tone={entry.latest_run?.error_summary ? "warn" : "default"}
      />
    </ConfigPanel>
  );
}

function AgentSettingsPanel({
  agentId,
  summary,
  entry,
  config,
  isLoadingConfig,
  configError,
  isEditing,
  draftValues,
  saveMessage,
  saveError,
  isSaving,
  onStartEdit,
  onCancelEdit,
  onFieldChange,
  onSave,
}: {
  agentId: AgentName;
  summary: SettingsSummaryResponse | undefined;
  entry: AgentStatusEntry | undefined;
  config: AgentConfigResponse | undefined;
  isLoadingConfig: boolean;
  configError: string | null;
  isEditing: boolean;
  draftValues: Record<string, string>;
  saveMessage: string | null;
  saveError: string | null;
  isSaving: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onFieldChange: (key: string, value: string) => void;
  onSave: () => void;
}) {
  function formatFieldValue(field: AgentConfigField, value: string): string {
    if (!value) {
      return field.input_kind === "csv" ? "none" : "Unavailable";
    }
    if (field.unit === "seconds") {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? formatDuration(parsed) : `${value} seconds`;
    }
    if (field.unit) {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? `${parsed.toLocaleString()} ${field.unit}` : `${value} ${field.unit}`;
    }
    return value;
  }

  function renderFieldInput(field: AgentConfigField) {
    const baseStyle: React.CSSProperties = {
      width: "100%",
      background: "var(--bg-2)",
      color: "var(--text-0)",
      border: "1px solid var(--border)",
      borderRadius: "8px",
      padding: "10px 12px",
      fontSize: "13px",
    };
    const value = draftValues[field.key] ?? field.value;

    if (field.input_kind === "csv") {
      return (
        <textarea
          value={value}
          onChange={(event) => onFieldChange(field.key, event.target.value)}
          placeholder={field.placeholder ?? undefined}
          rows={3}
          style={{ ...baseStyle, resize: "vertical", fontFamily: "var(--mono)" }}
        />
      );
    }

    return (
      <input
        type={field.input_kind === "date" ? "date" : "number"}
        value={value}
        min={field.min_value ?? undefined}
        onChange={(event) => onFieldChange(field.key, event.target.value)}
        placeholder={field.placeholder ?? undefined}
        style={{
          ...baseStyle,
          fontFamily: field.input_kind === "date" ? "inherit" : "var(--mono)",
        }}
      />
    );
  }

  const sharedPanelHeader = (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "12px",
        marginBottom: "12px",
      }}
    >
      <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-0)" }}>Agent Settings</div>
      {config?.editable ? (
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          {isEditing ? (
            <>
              <button
                type="button"
                onClick={onCancelEdit}
                disabled={isSaving}
                style={{
                  padding: "8px 12px",
                  background: "transparent",
                  color: "var(--text-1)",
                  border: "1px solid var(--border)",
                  borderRadius: "8px",
                  cursor: isSaving ? "wait" : "pointer",
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={onSave}
                disabled={isSaving}
                style={{
                  padding: "8px 12px",
                  background: "var(--amber-dim)",
                  color: "var(--amber)",
                  border: "1px solid rgba(201, 139, 27, 0.35)",
                  borderRadius: "8px",
                  cursor: isSaving ? "wait" : "pointer",
                  fontWeight: 600,
                }}
              >
                {isSaving ? "Saving..." : "Save Settings"}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={onStartEdit}
              style={{
                padding: "8px 12px",
                background: "var(--bg-3)",
                color: "var(--text-0)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                cursor: "pointer",
              }}
            >
              Edit Settings
            </button>
          )}
        </div>
      ) : null}
    </div>
  );

  if (EDITABLE_AGENT_IDS.includes(agentId)) {
    const fieldMap = new Map((config?.fields ?? []).map((field) => [field.key, field]));
    const firehosePerPageValue = draftValues.FIREHOSE_PER_PAGE ?? fieldMap.get("FIREHOSE_PER_PAGE")?.value ?? "0";
    const firehosePagesValue = draftValues.FIREHOSE_PAGES ?? fieldMap.get("FIREHOSE_PAGES")?.value ?? "0";
    const backfillPerPageValue = draftValues.BACKFILL_PER_PAGE ?? fieldMap.get("BACKFILL_PER_PAGE")?.value ?? "0";
    const backfillPagesValue = draftValues.BACKFILL_PAGES ?? fieldMap.get("BACKFILL_PAGES")?.value ?? "0";
    const firehoseEstimatedMax = Number(firehosePerPageValue) * Number(firehosePagesValue) * 2;
    const backfillEstimatedMax = Number(backfillPerPageValue) * Number(backfillPagesValue);

    return (
      <ConfigPanel title="">
        {sharedPanelHeader}
        {isLoadingConfig ? <p style={{ color: "var(--text-2)", fontSize: "12px" }}>Loading editable settings…</p> : null}
        {configError ? (
          <div style={{ color: "var(--red)", fontSize: "12px", marginBottom: "12px" }}>{configError}</div>
        ) : null}
        {saveError ? (
          <div style={{ color: "var(--red)", fontSize: "12px", marginBottom: "12px" }}>{saveError}</div>
        ) : null}
        {saveMessage ? (
          <div style={{ color: "var(--green)", fontSize: "12px", marginBottom: "12px" }}>{saveMessage}</div>
        ) : null}
        {config ? (
          <>
            <p style={{ color: "var(--text-1)", fontSize: "12px", lineHeight: 1.6, marginBottom: "12px" }}>
              {config.summary}
            </p>
            {isEditing ? (
              <div style={{ display: "grid", gap: "12px" }}>
                {config.fields.map((field) => (
                  <div key={field.key}>
                    <div style={{ fontSize: "12px", color: "var(--text-0)", fontWeight: 600, marginBottom: "6px" }}>
                      {field.label}
                    </div>
                    <div style={{ fontSize: "12px", color: "var(--text-2)", lineHeight: 1.5, marginBottom: "8px" }}>
                      {field.description}
                    </div>
                    {renderFieldInput(field)}
                  </div>
                ))}
              </div>
            ) : (
              <>
                {config.fields.map((field) => (
                  <DetailRow
                    key={field.key}
                    label={field.label}
                    value={formatFieldValue(field, field.value)}
                  />
                ))}
                {agentId === "firehose" ? (
                  <DetailRow
                    label="Estimated max fetched / run"
                    value={Number.isFinite(firehoseEstimatedMax) ? firehoseEstimatedMax.toLocaleString() : "Unavailable"}
                  />
                ) : null}
                {agentId === "backfill" ? (
                  <DetailRow
                    label="Estimated max fetched / run"
                    value={Number.isFinite(backfillEstimatedMax) ? backfillEstimatedMax.toLocaleString() : "Unavailable"}
                  />
                ) : null}
              </>
            )}
            <div style={{ marginTop: "14px", display: "grid", gap: "8px" }}>
              {config.apply_notes.map((note) => (
                <div key={note} style={{ fontSize: "12px", color: "var(--text-2)", lineHeight: 1.6 }}>
                  {note}
                </div>
              ))}
            </div>
          </>
        ) : null}
      </ConfigPanel>
    );
  }

  const intakePacing = findSettingEntry(summary, ["workers.INTAKE_PACING_SECONDS", "INTAKE_PACING_SECONDS"]);
  const githubRpm = findSettingEntry(summary, ["workers.GITHUB_REQUESTS_PER_MINUTE", "GITHUB_REQUESTS_PER_MINUTE"]);
  const firehoseInterval = findSettingEntry(summary, ["workers.FIREHOSE_INTERVAL_SECONDS", "FIREHOSE_INTERVAL_SECONDS"]);
  const firehosePerPage = findSettingEntry(summary, ["workers.FIREHOSE_PER_PAGE", "FIREHOSE_PER_PAGE"]);
  const firehosePages = findSettingEntry(summary, ["workers.FIREHOSE_PAGES", "FIREHOSE_PAGES"]);
  const backfillInterval = findSettingEntry(summary, ["workers.BACKFILL_INTERVAL_SECONDS", "BACKFILL_INTERVAL_SECONDS"]);
  const backfillPerPage = findSettingEntry(summary, ["workers.BACKFILL_PER_PAGE", "BACKFILL_PER_PAGE"]);
  const backfillPages = findSettingEntry(summary, ["workers.BACKFILL_PAGES", "BACKFILL_PAGES"]);
  const backfillWindowDays = findSettingEntry(summary, ["workers.BACKFILL_WINDOW_DAYS", "BACKFILL_WINDOW_DAYS"]);
  const backfillMinDate = findSettingEntry(summary, ["workers.BACKFILL_MIN_CREATED_DATE", "BACKFILL_MIN_CREATED_DATE"]);
  const bouncerIncludeRules = findSettingEntry(summary, ["workers.BOUNCER_INCLUDE_RULES", "BOUNCER_INCLUDE_RULES"]);
  const bouncerExcludeRules = findSettingEntry(summary, ["workers.BOUNCER_EXCLUDE_RULES", "BOUNCER_EXCLUDE_RULES"]);

  if (agentId === "firehose") {
    const perPage = Number(firehosePerPage?.value ?? "0");
    const pages = Number(firehosePages?.value ?? "0");
    const estimatedPerRun = Number.isFinite(perPage) && Number.isFinite(pages) ? perPage * pages * 2 : null;
    return (
      <ConfigPanel title="Agent Settings">
        <DetailRow label="Interval" value={firehoseInterval?.value ? formatDuration(Number(firehoseInterval.value)) : "Unavailable"} />
        <DetailRow label="Page size" value={firehosePerPage?.value ?? "Unavailable"} />
        <DetailRow label="Pages per mode" value={firehosePages?.value ?? "Unavailable"} />
        <DetailRow label="Discovery modes" value="2 (new + trending)" />
        <DetailRow label="Estimated max fetched / run" value={estimatedPerRun != null ? estimatedPerRun.toLocaleString() : "Unavailable"} />
        <DetailRow label="GitHub request budget" value={githubRpm?.value ? `${githubRpm.value} req/min` : "Unavailable"} />
        <DetailRow label="Inter-job pacing" value={intakePacing?.value ? formatDuration(Number(intakePacing.value)) : "Unavailable"} />
      </ConfigPanel>
    );
  }

  if (agentId === "backfill") {
    const perPage = Number(backfillPerPage?.value ?? "0");
    const pages = Number(backfillPages?.value ?? "0");
    const estimatedPerRun = Number.isFinite(perPage) && Number.isFinite(pages) ? perPage * pages : null;
    return (
      <ConfigPanel title="Agent Settings">
        <DetailRow label="Interval" value={backfillInterval?.value ? formatDuration(Number(backfillInterval.value)) : "Unavailable"} />
        <DetailRow label="Page size" value={backfillPerPage?.value ?? "Unavailable"} />
        <DetailRow label="Pages per run" value={backfillPages?.value ?? "Unavailable"} />
        <DetailRow label="Estimated max fetched / run" value={estimatedPerRun != null ? estimatedPerRun.toLocaleString() : "Unavailable"} />
        <DetailRow label="Window size" value={backfillWindowDays?.value ? `${backfillWindowDays.value} days` : "Unavailable"} />
        <DetailRow label="Oldest repo date" value={backfillMinDate?.value ?? "Unavailable"} />
        <DetailRow label="GitHub request budget" value={githubRpm?.value ? `${githubRpm.value} req/min` : "Unavailable"} />
        <DetailRow label="Inter-job pacing" value={intakePacing?.value ? formatDuration(Number(intakePacing.value)) : "Unavailable"} />
      </ConfigPanel>
    );
  }

  if (agentId === "bouncer") {
    return (
      <ConfigPanel title="Agent Settings">
        <DetailRow label="Execution mode" value="Queue-driven" />
        <DetailRow label="Include rules" value={bouncerIncludeRules?.value ?? "none"} />
        <DetailRow label="Exclude rules" value={bouncerExcludeRules?.value ?? "none"} />
        <DetailRow label="Inter-job pacing" value={intakePacing?.value ? formatDuration(Number(intakePacing.value)) : "Unavailable"} />
      </ConfigPanel>
    );
  }

  if (agentId === "analyst") {
    return (
      <ConfigPanel title="Agent Settings">
        <DetailRow label="Execution mode" value="Queue-driven" />
        <DetailRow label="Provider" value={entry?.configured_provider ?? "None"} />
        <DetailRow label="Model" value={entry?.configured_model ?? "None"} />
        <DetailRow label="Uses LLM" value={entry?.uses_model ? "Yes" : "No"} tone={entry?.uses_model ? "warn" : "good"} />
        <DetailRow label="Dedicated cadence" value="Not exposed yet" />
      </ConfigPanel>
    );
  }

  return (
    <ConfigPanel title="Agent Settings">
      <DetailRow label="Execution mode" value={agentId === "combiner" || agentId === "obsession" || agentId === "overlord" ? "Manual / workflow-driven" : "Unavailable"} />
      <DetailRow label="Provider" value={entry?.configured_provider ?? "None"} />
      <DetailRow label="Model" value={entry?.configured_model ?? "None"} />
      <DetailRow label="Dedicated cadence" value="No editable runtime controls exposed yet" />
    </ConfigPanel>
  );
}

function MetadataNotice({ entry }: { entry: AgentStatusEntry | undefined }) {
  if (!entry) {
    return null;
  }

  return (
    <div
      style={{
        background: entry.uses_model ? "var(--blue-dim)" : "var(--bg-3)",
        border: `1px solid ${entry.uses_model ? "var(--blue)" : "var(--border)"}`,
        borderRadius: "10px",
        padding: "12px",
        marginBottom: "16px",
        fontSize: "12px",
        color: "var(--text-2)",
      }}
    >
      <strong style={{ color: entry.uses_model ? "var(--blue)" : "var(--text-0)" }}>
        ℹ️ Runtime:
      </strong>{" "}
      {entry.description} Provider: {entry.configured_provider ?? "none"}. Model:{" "}
      {entry.configured_model ?? "none"}.
    </div>
  );
}

function RuntimeQueuePanels({
  queue,
  latestRun,
  agentId,
  backfillTimeline,
  isEditingBackfillTimeline,
  backfillTimelineDraft,
  backfillTimelineSaveMessage,
  backfillTimelineSaveError,
  isSavingBackfillTimeline,
  onStartEditBackfillTimeline,
  onCancelEditBackfillTimeline,
  onChangeBackfillTimeline,
  onSaveBackfillTimeline,
}: {
  queue: GatewayAgentIntakeQueueSummary | null;
  latestRun: AgentStatusEntry["latest_run"] | null | undefined;
  agentId: AgentName;
  backfillTimeline: BackfillTimelineResponse | undefined;
  isEditingBackfillTimeline: boolean;
  backfillTimelineDraft: { oldest_date_in_window: string; newest_boundary_exclusive: string };
  backfillTimelineSaveMessage: string | null;
  backfillTimelineSaveError: string | null;
  isSavingBackfillTimeline: boolean;
  onStartEditBackfillTimeline: () => void;
  onCancelEditBackfillTimeline: () => void;
  onChangeBackfillTimeline: (
    key: "oldest_date_in_window" | "newest_boundary_exclusive",
    value: string,
  ) => void;
  onSaveBackfillTimeline: () => void;
}) {
  if (!queue) {
    return (
      <ConfigPanel title="Runtime Queue">
        <DetailRow label="Status" value="Not exposed on this surface" />
      </ConfigPanel>
    );
  }

  const showBackfillEmptyState =
    agentId === "backfill" &&
    queue.total_items === 0 &&
    Boolean(queue.checkpoint.last_checkpointed_at) &&
    (latestRun?.items_processed ?? 0) === 0;

  const isBackfillCheckpoint = "window_start_date" in queue.checkpoint;
  const isFirehoseCheckpoint = "active_mode" in queue.checkpoint;

  const timelinePanel = isBackfillCheckpoint ? (
    <ConfigPanel title="Timeline Window">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "12px",
          marginBottom: "12px",
        }}
      >
        <div style={{ fontSize: "12px", color: "var(--text-2)", lineHeight: 1.6 }}>
          Backfill scans a historical creation-date window, starting from the newer boundary side
          and then moving that whole window backward over time.
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          {isEditingBackfillTimeline ? (
            <>
              <button
                type="button"
                onClick={onCancelEditBackfillTimeline}
                disabled={isSavingBackfillTimeline}
                style={{
                  padding: "8px 12px",
                  background: "transparent",
                  color: "var(--text-1)",
                  border: "1px solid var(--border)",
                  borderRadius: "8px",
                  cursor: isSavingBackfillTimeline ? "wait" : "pointer",
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={onSaveBackfillTimeline}
                disabled={isSavingBackfillTimeline}
                style={{
                  padding: "8px 12px",
                  background: "var(--amber-dim)",
                  color: "var(--amber)",
                  border: "1px solid rgba(201, 139, 27, 0.35)",
                  borderRadius: "8px",
                  cursor: isSavingBackfillTimeline ? "wait" : "pointer",
                  fontWeight: 600,
                }}
              >
                {isSavingBackfillTimeline ? "Saving..." : "Save Timeline"}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={onStartEditBackfillTimeline}
              style={{
                padding: "8px 12px",
                background: "var(--bg-3)",
                color: "var(--text-0)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                cursor: "pointer",
              }}
            >
              Edit Timeline
            </button>
          )}
        </div>
      </div>
      {backfillTimelineSaveMessage ? (
        <div style={{ color: "var(--green)", fontSize: "12px", marginBottom: "12px" }}>
          {backfillTimelineSaveMessage}
        </div>
      ) : null}
      {backfillTimelineSaveError ? (
        <div style={{ color: "var(--red)", fontSize: "12px", marginBottom: "12px" }}>
          {backfillTimelineSaveError}
        </div>
      ) : null}
      <DetailRow label="Timeline basis" value="GitHub repository created date" />
      {isEditingBackfillTimeline ? (
        <div style={{ display: "grid", gap: "12px", marginBottom: "12px" }}>
          <div>
            <div style={{ fontSize: "12px", color: "var(--text-0)", fontWeight: 600, marginBottom: "6px" }}>
              Oldest date included in this window
            </div>
            <div style={{ fontSize: "12px", color: "var(--text-2)", lineHeight: 1.5, marginBottom: "8px" }}>
              Backfill includes repositories created on or after this date.
            </div>
            <input
              type="date"
              value={backfillTimelineDraft.oldest_date_in_window}
              onChange={(event) => onChangeBackfillTimeline("oldest_date_in_window", event.target.value)}
              style={{
                width: "100%",
                background: "var(--bg-2)",
                color: "var(--text-0)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                padding: "10px 12px",
                fontSize: "13px",
              }}
            />
          </div>
          <div>
            <div style={{ fontSize: "12px", color: "var(--text-0)", fontWeight: 600, marginBottom: "6px" }}>
              Newest boundary to start from
            </div>
            <div style={{ fontSize: "12px", color: "var(--text-2)", lineHeight: 1.5, marginBottom: "8px" }}>
              Backfill starts from this newer edge and scans repositories created before it.
            </div>
            <input
              type="date"
              value={backfillTimelineDraft.newest_boundary_exclusive}
              onChange={(event) => onChangeBackfillTimeline("newest_boundary_exclusive", event.target.value)}
              style={{
                width: "100%",
                background: "var(--bg-2)",
                color: "var(--text-0)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                padding: "10px 12px",
                fontSize: "13px",
              }}
            />
          </div>
        </div>
      ) : null}
      <DetailRow
        label="Oldest date included in this window"
        value={backfillTimeline?.oldest_date_in_window ?? queue.checkpoint.window_start_date ?? "Unavailable"}
      />
      <DetailRow
        label="Newest boundary to start from"
        value={backfillTimeline?.newest_boundary_exclusive ?? queue.checkpoint.created_before_boundary ?? "Unavailable"}
      />
      <DetailRow
        label="Current timestamp cursor inside this window"
        value={backfillTimeline?.current_cursor ?? queue.checkpoint.created_before_cursor ?? "Not currently narrowed inside the window"}
      />
      <DetailRow
        label="Current historical span"
        value={
          (backfillTimeline?.oldest_date_in_window ?? queue.checkpoint.window_start_date) &&
          (backfillTimeline?.newest_boundary_exclusive ?? queue.checkpoint.created_before_boundary)
            ? `${backfillTimeline?.oldest_date_in_window ?? queue.checkpoint.window_start_date} through ${subtractOneDay(
                backfillTimeline?.newest_boundary_exclusive ?? queue.checkpoint.created_before_boundary,
              )}`
            : "Window not fully established yet"
        }
      />
      <div
        style={{
          marginTop: "10px",
          marginBottom: "10px",
          padding: "10px 12px",
          background: "var(--bg-3)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          fontSize: "12px",
          color: "var(--text-1)",
          lineHeight: 1.6,
        }}
      >
        {(() => {
          const oldestDate =
            backfillTimeline?.oldest_date_in_window ?? queue.checkpoint.window_start_date;
          const newestBoundary =
            backfillTimeline?.newest_boundary_exclusive ?? queue.checkpoint.created_before_boundary;
          const newestIncludedDate = subtractOneDay(newestBoundary);

          if (!oldestDate || !newestBoundary || !newestIncludedDate) {
            return "Next Backfill run span is not fully established yet.";
          }

          return `Next Backfill run will scan repositories created from ${oldestDate} through ${newestIncludedDate}. It begins from the newer side near ${newestIncludedDate} and moves backward inside that window.`;
        })()}
      </div>
      <div style={{ fontSize: "12px", color: "var(--text-2)", lineHeight: 1.6 }}>
        The newest boundary is exclusive. For example, a boundary of `2025-10-15` means the newest
        included repositories were created on `2025-10-14`.
      </div>
    </ConfigPanel>
  ) : isFirehoseCheckpoint ? (
    <ConfigPanel title="Timeline Window">
      <DetailRow label="Timeline Basis" value="Live GitHub feeds" />
      <DetailRow
        label="Active Feed"
        value={queue.checkpoint.active_mode ? titleCase(queue.checkpoint.active_mode) : "Idle"}
      />
      <DetailRow
        label="New Feed Anchor"
        value={queue.checkpoint.new_anchor_date ?? "Unavailable"}
      />
      <DetailRow
        label="Trending Feed Anchor"
        value={queue.checkpoint.trending_anchor_date ?? "Unavailable"}
      />
      <DetailRow
        label="Currently Monitoring"
        value={
          queue.checkpoint.active_mode === "new" && queue.checkpoint.new_anchor_date
            ? `NEW feed since ${queue.checkpoint.new_anchor_date}`
            : queue.checkpoint.active_mode === "trending" &&
                queue.checkpoint.trending_anchor_date
              ? `TRENDING feed anchored at ${queue.checkpoint.trending_anchor_date}`
              : "Waiting for the next feed poll"
        }
      />
      <p style={{ color: "var(--text-2)", fontSize: "12px", lineHeight: 1.6 }}>
        Firehose tracks two live feeds. Each run records whether intake came from the NEW feed or
        the TRENDING feed, and those provenance tags now follow the repository into the catalog.
      </p>
    </ConfigPanel>
  ) : null;

  return (
    <>
      {showBackfillEmptyState ? (
        <ConfigPanel title="Operator Note">
          <p style={{ color: "var(--text-1)", fontSize: "12px", lineHeight: 1.6 }}>
            Backfill is checkpointing, but the current database has no repositories attributed to
            Backfill yet. The repositories catalog can honestly show zero Backfill rows while this
            panel still shows an active checkpoint.
          </p>
        </ConfigPanel>
      ) : null}

      <ConfigPanel title="Queue State">
        <DetailRow label="Pending" value={queue.state_counts.pending.toLocaleString()} />
        <DetailRow label="In Progress" value={queue.state_counts.in_progress.toLocaleString()} />
        <DetailRow label="Completed" value={queue.state_counts.completed.toLocaleString()} />
        <DetailRow label="Failed" value={queue.state_counts.failed.toLocaleString()} />
        <DetailRow label="Total" value={queue.total_items.toLocaleString()} />
      </ConfigPanel>

      {timelinePanel}

      <ConfigPanel title="Checkpoint">
        <DetailRow label="Next Page" value={queue.checkpoint.next_page} />
        <DetailRow
          label="Progress last saved at"
          value={
            queue.checkpoint.last_checkpointed_at
              ? `${formatRelative(queue.checkpoint.last_checkpointed_at)} (${formatTimestamp(queue.checkpoint.last_checkpointed_at)})`
              : "Never"
          }
        />
        {"window_start_date" in queue.checkpoint ? (
          <>
            <DetailRow
              label="Exhausted"
              value={queue.checkpoint.exhausted ? "Yes" : "No"}
              tone={queue.checkpoint.exhausted ? "good" : "default"}
            />
          </>
        ) : (
          <>
            <DetailRow
              label="Resume Required"
              value={queue.checkpoint.resume_required ? "Yes" : "No"}
            />
          </>
        )}
        <DetailRow
          label="Latest Run"
          value={
            latestRun?.started_at
              ? `${titleCase(latestRun.status)} · ${formatRelative(latestRun.started_at)}`
              : "No run recorded"
          }
        />
      </ConfigPanel>
    </>
  );
}

function AnalystPanels({ entry }: { entry: AgentStatusEntry | undefined }) {
  if (!entry) {
    return null;
  }

  return (
    <>
      <ConfigPanel title="Analysis Runtime">
        <DetailRow label="Implementation" value={titleCase(entry.runtime_kind)} />
        <DetailRow label="Provider" value={entry.configured_provider ?? "Unavailable"} />
        <DetailRow label="Model" value={entry.configured_model ?? "None"} />
        <DetailRow
          label="Uses LLM"
          value={entry.uses_model ? "Yes" : "No"}
          tone={entry.uses_model ? "warn" : "good"}
        />
      </ConfigPanel>

      <ConfigPanel title="Notes">
        {entry.notes.map((note) => (
          <p key={note} style={{ color: "var(--text-1)", fontSize: "12px", marginBottom: "10px" }}>
            {note}
          </p>
        ))}
      </ConfigPanel>
    </>
  );
}

function MetadataPanels({ entry }: { entry: AgentStatusEntry | undefined }) {
  if (!entry) {
    return null;
  }

  return (
    <>
      <ConfigPanel title="Runtime">
        <DetailRow label="Implementation" value={titleCase(entry.implementation_status)} />
        <DetailRow label="Runtime Kind" value={titleCase(entry.runtime_kind)} />
        <DetailRow label="Provider" value={entry.configured_provider ?? "None"} />
        <DetailRow label="Model" value={entry.configured_model ?? "None"} />
      </ConfigPanel>

      <ConfigPanel title="Notes">
        {entry.notes.map((note) => (
          <p key={note} style={{ color: "var(--text-1)", fontSize: "12px", marginBottom: "10px" }}>
            {note}
          </p>
        ))}
      </ConfigPanel>
    </>
  );
}

export default function ControlPanel() {
  const [selectedAgent, setSelectedAgent] = useState<AgentName>("firehose");
  const [isEditingConfig, setIsEditingConfig] = useState(false);
  const [draftConfigValues, setDraftConfigValues] = useState<Record<string, string>>({});
  const [configSaveMessage, setConfigSaveMessage] = useState<string | null>(null);
  const [isEditingBackfillTimeline, setIsEditingBackfillTimeline] = useState(false);
  const [backfillTimelineDraft, setBackfillTimelineDraft] = useState<{
    oldest_date_in_window: string;
    newest_boundary_exclusive: string;
  }>({
    oldest_date_in_window: "",
    newest_boundary_exclusive: "",
  });
  const [backfillTimelineSaveMessage, setBackfillTimelineSaveMessage] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const pauseStatesQuery = useQuery({
    queryKey: getAgentPauseStatesQueryKey(),
    queryFn: fetchAgentPauseStates,
    refetchInterval: 5000,
  });
  const latestRunsQuery = useQuery({
    queryKey: getLatestAgentRunsQueryKey(),
    queryFn: fetchLatestAgentRuns,
    refetchInterval: 30_000,
  });
  const gatewayRuntimeQuery = useQuery({
    queryKey: ["gateway", "runtime"],
    queryFn: fetchGatewayRuntime,
    refetchInterval: 30_000,
  });
  const settingsSummaryQuery = useQuery({
    queryKey: ["settings", "summary"],
    queryFn: fetchSettingsSummary,
    refetchInterval: 60_000,
  });
  const agentConfigQuery = useQuery({
    queryKey: getAgentConfigQueryKey(selectedAgent),
    queryFn: () => fetchAgentConfig(selectedAgent),
    enabled: EDITABLE_AGENT_IDS.includes(selectedAgent),
    refetchInterval: 60_000,
  });
  const backfillTimelineQuery = useQuery({
    queryKey: getBackfillTimelineQueryKey(),
    queryFn: fetchBackfillTimeline,
    enabled: selectedAgent === "backfill",
    refetchInterval: 60_000,
  });

  const pauseMutation = useMutation({
    mutationFn: ({ agent, reason }: { agent: AgentName; reason: string }) =>
      pauseAgent(agent, reason, "manual"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: getAgentPauseStatesQueryKey() });
    },
  });

  const resumeMutation = useMutation({
    mutationFn: (agent: AgentName) => resumeAgent(agent),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: getAgentPauseStatesQueryKey() });
    },
  });
  const triggerRunMutation = useMutation({
    mutationFn: (agent: AgentName) => triggerAgentRun(agent),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: getLatestAgentRunsQueryKey() });
      void queryClient.invalidateQueries({ queryKey: ["gateway", "runtime"] });
    },
  });
  const configSaveMutation = useMutation({
    mutationFn: (values: Record<string, string>) => updateAgentConfig(selectedAgent, values),
    onSuccess: (data) => {
      setConfigSaveMessage(data.message);
      setIsEditingConfig(false);
      setDraftConfigValues(
        Object.fromEntries(data.fields.map((field) => [field.key, field.value])),
      );
      void queryClient.invalidateQueries({ queryKey: getAgentConfigQueryKey(selectedAgent) });
      void queryClient.invalidateQueries({ queryKey: ["settings", "summary"] });
    },
  });
  const backfillTimelineMutation = useMutation({
    mutationFn: (values: { oldest_date_in_window: string; newest_boundary_exclusive: string }) =>
      updateBackfillTimeline(values),
    onSuccess: (data) => {
      setBackfillTimelineSaveMessage(data.message);
      setIsEditingBackfillTimeline(false);
      setBackfillTimelineDraft({
        oldest_date_in_window: data.oldest_date_in_window,
        newest_boundary_exclusive: data.newest_boundary_exclusive,
      });
      void queryClient.invalidateQueries({ queryKey: getBackfillTimelineQueryKey() });
      void queryClient.invalidateQueries({ queryKey: ["gateway", "runtime"] });
      void queryClient.invalidateQueries({ queryKey: getLatestAgentRunsQueryKey() });
    },
  });

  const currentAgent = AGENTS.find((agent) => agent.id === selectedAgent) ?? AGENTS[0];
  const agentPauseState = pauseStatesQuery.data?.find((state) => state.agent_name === selectedAgent);
  const agentStatus = latestRunsQuery.data?.agents.find((agent) => agent.agent_name === selectedAgent);
  const runtimeAgent = gatewayRuntimeQuery.data?.runtime.agent_states.find(
    (agent) => agent.agent_key === selectedAgent,
  );
  const runtimeQueue = runtimeAgent && isLiveIntakeQueue(runtimeAgent.queue) ? runtimeAgent.queue : null;
  const isPaused = agentPauseState?.is_paused ?? false;
  const usesModel = agentStatus?.uses_model ?? false;
  const cadence = deriveCadenceForAgent({
    agentId: selectedAgent,
    isPaused,
    pauseReason: agentPauseState?.pause_reason,
    runtimeQueue,
    latestRun: agentStatus?.latest_run,
    settingsSummary: settingsSummaryQuery.data,
  });

  const loadingMessage = useMemo(() => {
    if (latestRunsQuery.isLoading || pauseStatesQuery.isLoading || settingsSummaryQuery.isLoading) {
      return "Loading control panel state...";
    }
    return null;
  }, [latestRunsQuery.isLoading, pauseStatesQuery.isLoading, settingsSummaryQuery.isLoading]);

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Control Panel</span>
        <span className="topbar-breadcrumb">agent control</span>
      </div>

      <div style={{ display: "flex", height: "calc(100vh - 44px)", minHeight: 0 }}>
        <div
          style={{
            width: "240px",
            background: "var(--bg-1)",
            borderRight: "1px solid var(--border)",
            padding: "16px",
            overflowY: "auto",
          }}
        >
          <div className="card-label" style={{ marginBottom: "12px" }}>
            Agents
          </div>
          {AGENTS.map((agent) => {
            const state = pauseStatesQuery.data?.find((entry) => entry.agent_name === agent.id);
            return (
              <AgentBtn
                key={agent.id}
                agent={agent}
                active={selectedAgent === agent.id}
                paused={state?.is_paused ?? false}
                onClick={() => {
                  setSelectedAgent(agent.id);
                  setIsEditingConfig(false);
                  setConfigSaveMessage(null);
                  setDraftConfigValues({});
                  setIsEditingBackfillTimeline(false);
                  setBackfillTimelineSaveMessage(null);
                  setBackfillTimelineDraft({
                    oldest_date_in_window: "",
                    newest_boundary_exclusive: "",
                  });
                  configSaveMutation.reset();
                  backfillTimelineMutation.reset();
                }}
              />
            );
          })}
        </div>

        <div style={{ flex: 1, padding: "24px", overflow: "auto", minHeight: 0 }}>
          <div style={{ maxWidth: "960px" }}>
            <div className="card" style={{ marginBottom: "20px" }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  gap: "16px",
                  marginBottom: "16px",
                }}
              >
                <div>
                  <h2
                    style={{
                      fontSize: "20px",
                      fontWeight: 600,
                      color: "var(--text-0)",
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      flexWrap: "wrap",
                    }}
                  >
                    <span>{currentAgent.icon}</span>
                    <span>{currentAgent.label}</span>
                    {usesModel ? <span className="badge badge-blue">LLM-backed</span> : null}
                    {agentStatus?.configured_provider ? (
                      <span className="badge badge-yellow">{titleCase(agentStatus.configured_provider)}</span>
                    ) : null}
                  </h2>
                  <div style={{ fontSize: "12px", color: "var(--text-2)", marginTop: "4px" }}>
                    {agentStatus?.description ?? currentAgent.fallbackDescription}
                  </div>
                </div>
                <span
                  className={`badge ${
                    isPaused ? "badge-red" : cadence.mode === "interval" && cadence.remainingSeconds && cadence.remainingSeconds > 0 ? "badge-yellow" : "badge-green"
                  }`}
                >
                  {cadence.stateLabel}
                </span>
              </div>

              <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                {isPaused ? (
                  <button
                    type="button"
                    onClick={() => resumeMutation.mutate(selectedAgent)}
                    disabled={resumeMutation.isPending}
                    style={{
                      padding: "8px 16px",
                      background: "var(--green)",
                      color: "var(--bg-0)",
                      border: "none",
                      borderRadius: "6px",
                      fontSize: "12px",
                      fontWeight: 600,
                      cursor: resumeMutation.isPending ? "wait" : "pointer",
                      opacity: resumeMutation.isPending ? 0.6 : 1,
                    }}
                  >
                    ▶ Resume Agent
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() =>
                      pauseMutation.mutate({
                        agent: selectedAgent,
                        reason: "Manual pause from control panel",
                      })
                    }
                    disabled={pauseMutation.isPending}
                    style={{
                      padding: "8px 16px",
                      background: "var(--yellow)",
                      color: "var(--bg-0)",
                      border: "none",
                      borderRadius: "6px",
                      fontSize: "12px",
                      fontWeight: 600,
                      cursor: pauseMutation.isPending ? "wait" : "pointer",
                      opacity: pauseMutation.isPending ? 0.6 : 1,
                    }}
                  >
                    ⏸ Pause Agent
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    if (cadence.actionAvailable) {
                      triggerRunMutation.mutate(selectedAgent);
                    }
                  }}
                  disabled={!cadence.actionAvailable}
                  title={cadence.actionReason ?? undefined}
                  style={{
                    padding: "8px 16px",
                    background: "var(--bg-3)",
                    color: cadence.actionAvailable ? "var(--text-0)" : "var(--text-2)",
                    border: "1px solid var(--border)",
                    borderRadius: "6px",
                    fontSize: "12px",
                    fontWeight: 600,
                    cursor:
                      cadence.actionAvailable && !triggerRunMutation.isPending
                        ? "pointer"
                        : "not-allowed",
                    opacity:
                      cadence.actionAvailable && !triggerRunMutation.isPending ? 1 : 0.65,
                  }}
                >
                  ⚡ {cadence.actionLabel}
                </button>
              </div>

              <div style={{ display: "grid", gap: "10px", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", marginTop: "16px" }}>
                <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
                  <div className="card-label">Latest Run</div>
                  <div style={{ color: "var(--text-0)", marginTop: "6px", fontWeight: 600 }}>
                    {agentStatus?.latest_run?.started_at
                      ? `${titleCase(agentStatus.latest_run.status)} · ${formatRelative(agentStatus.latest_run.started_at)}`
                      : "No run recorded"}
                  </div>
                </div>
                <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
                  <div className="card-label">Items Processed</div>
                  <div style={{ color: "var(--text-0)", marginTop: "6px", fontWeight: 600 }}>
                    {agentStatus?.latest_run?.items_processed?.toLocaleString() ?? "Unavailable"}
                  </div>
                </div>
                <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
                  <div className="card-label">Run Duration</div>
                  <div style={{ color: "var(--text-0)", marginTop: "6px", fontWeight: 600 }}>
                    {formatDuration(agentStatus?.latest_run?.duration_seconds)}
                  </div>
                </div>
                <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
                  <div className="card-label">Token Usage (24h)</div>
                  <div style={{ color: "var(--text-0)", marginTop: "6px", fontWeight: 600 }}>
                    {agentStatus ? formatTokens(agentStatus.token_usage_24h) : "Unavailable"}
                  </div>
                </div>
                <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
                  <div className="card-label">Scheduled Run</div>
                  <div style={{ color: "var(--text-0)", marginTop: "6px", fontWeight: 600 }}>
                    {cadence.nextDueAt
                      ? formatTimestamp(cadence.nextDueAt)
                      : cadence.mode === "interval"
                        ? "Not scheduled yet"
                        : "On demand"}
                  </div>
                </div>
                <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
                  <div className="card-label">Time Until Run</div>
                  <div style={{ color: "var(--text-0)", marginTop: "6px", fontWeight: 600 }}>
                    {cadence.mode === "interval"
                      ? formatTimeUntilScheduledRun(cadence.nextDueAt)
                      : "N/A"}
                  </div>
                </div>
              </div>

              <div
                style={{
                  marginTop: "16px",
                  padding: "12px",
                  background: "var(--bg-3)",
                  border: "1px solid var(--border)",
                  borderRadius: "8px",
                }}
              >
                <div className="card-label" style={{ marginBottom: "10px" }}>
                  Scheduler state
                </div>
                <div style={{ color: "var(--text-1)", fontSize: "12px", lineHeight: 1.6 }}>
                  {cadence.explanation}
                </div>
                <div style={{ display: "grid", gap: "10px", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", marginTop: "12px" }}>
                  <div>
                    <div className="card-label">Scheduler health</div>
                    <div
                      style={{
                        color:
                          cadence.schedulerStatusTone === "good"
                            ? "var(--green)"
                            : cadence.schedulerStatusTone === "warn"
                              ? "var(--amber)"
                              : "var(--text-0)",
                        marginTop: "6px",
                        fontWeight: 600,
                      }}
                    >
                      {cadence.schedulerStatusLabel}
                    </div>
                  </div>
                  <div>
                    <div className="card-label">Last scheduler evidence</div>
                    <div style={{ color: "var(--text-0)", marginTop: "6px", fontWeight: 600 }}>
                      {formatEvidenceTimestamp(cadence.lastSchedulerEvidenceAt)}
                    </div>
                  </div>
                </div>
                <div style={{ marginTop: "12px", fontSize: "12px", color: "var(--text-1)", lineHeight: 1.6 }}>
                  {cadence.schedulerStatusExplanation}
                </div>
                {cadence.progressRatio != null ? (
                  <div style={{ marginTop: "12px" }}>
                    <div
                      style={{
                        height: "8px",
                        borderRadius: "999px",
                        background: "var(--bg-1)",
                        overflow: "hidden",
                        border: "1px solid var(--border)",
                      }}
                    >
                      <div
                        style={{
                          height: "100%",
                          width: `${Math.max(6, Math.round(cadence.progressRatio * 100))}%`,
                          background:
                            cadence.remainingSeconds && cadence.remainingSeconds > 0
                              ? "var(--amber)"
                              : "var(--green)",
                          transition: "width 200ms ease",
                        }}
                      />
                    </div>
                  </div>
                ) : null}
                {cadence.actionReason ? (
                  <div style={{ marginTop: "10px", fontSize: "11px", color: "var(--text-2)" }}>
                    {cadence.actionReason}
                  </div>
                ) : null}
                {triggerRunMutation.isSuccess ? (
                  <div style={{ marginTop: "10px", fontSize: "11px", color: "var(--green)" }}>
                    {triggerRunMutation.data.message}
                  </div>
                ) : null}
                {triggerRunMutation.error instanceof Error ? (
                  <div style={{ marginTop: "10px", fontSize: "11px", color: "var(--red)" }}>
                    {triggerRunMutation.error.message}
                  </div>
                ) : null}
              </div>

              {agentPauseState?.paused_at ? (
                <div
                  style={{
                    marginTop: "16px",
                    padding: "12px",
                    background: "var(--bg-3)",
                    border: "1px solid var(--border)",
                    borderRadius: "6px",
                    fontSize: "11px",
                    color: "var(--text-2)",
                  }}
                >
                  <div>
                    <strong style={{ color: "var(--text-0)" }}>Paused at:</strong>{" "}
                    {new Date(agentPauseState.paused_at).toLocaleString()}
                  </div>
                  {agentPauseState.pause_reason ? (
                    <div style={{ marginTop: "4px" }}>
                      <strong style={{ color: "var(--text-0)" }}>Reason:</strong>{" "}
                      {agentPauseState.pause_reason}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>

            {loadingMessage ? (
              <div className="card" style={{ marginBottom: "16px" }}>
                <p style={{ color: "var(--text-2)" }}>{loadingMessage}</p>
              </div>
            ) : null}

            <MetadataNotice entry={agentStatus} />

            <LatestRunPanel entry={agentStatus} />

            <ConfigPanel title="Cadence">
              <DetailRow label="Execution mode" value={titleCase(cadence.mode)} />
              <DetailRow label="State" value={cadence.stateLabel} />
              <DetailRow
                label="Interval"
                value={cadence.intervalSeconds != null ? formatDuration(cadence.intervalSeconds) : "Not recurring"}
              />
              <DetailRow
                label="Last checkpoint"
                value={cadence.lastCheckpointAt ? `${formatRelative(cadence.lastCheckpointAt)} (${formatTimestamp(cadence.lastCheckpointAt)})` : "Never"}
              />
              <DetailRow
                label="Scheduled run"
                value={
                  cadence.nextDueAt
                    ? `${formatTimeUntilScheduledRun(cadence.nextDueAt)} (${formatTimestamp(cadence.nextDueAt)})`
                    : cadence.mode === "interval"
                      ? "Not scheduled yet"
                      : "Triggered by work, not by time"
                }
              />
              <DetailRow
                label="Time until run"
                value={cadence.mode === "interval" ? formatTimeUntilScheduledRun(cadence.nextDueAt) : "N/A"}
                tone={cadence.mode === "interval" && (cadence.remainingSeconds ?? 0) <= 0 ? "good" : "default"}
              />
            </ConfigPanel>

            <AgentSettingsPanel
              agentId={selectedAgent}
              summary={settingsSummaryQuery.data}
              entry={agentStatus}
              config={agentConfigQuery.data}
              isLoadingConfig={agentConfigQuery.isLoading}
              configError={agentConfigQuery.error instanceof Error ? agentConfigQuery.error.message : null}
              isEditing={isEditingConfig}
              draftValues={draftConfigValues}
              saveMessage={configSaveMessage}
              saveError={configSaveMutation.error instanceof Error ? configSaveMutation.error.message : null}
              isSaving={configSaveMutation.isPending}
              onStartEdit={() => {
                if (agentConfigQuery.data) {
                  setDraftConfigValues(
                    Object.fromEntries(agentConfigQuery.data.fields.map((field) => [field.key, field.value])),
                  );
                }
                setConfigSaveMessage(null);
                setIsEditingConfig(true);
              }}
              onCancelEdit={() => {
                setDraftConfigValues({});
                setIsEditingConfig(false);
              }}
              onFieldChange={(key, value) => {
                setConfigSaveMessage(null);
                setDraftConfigValues((current) => ({ ...current, [key]: value }));
              }}
              onSave={() => configSaveMutation.mutate(draftConfigValues)}
            />

            {selectedAgent === "firehose" ? (
              <>
                <RuntimeQueuePanels
                  agentId={selectedAgent}
                  queue={runtimeQueue}
                  latestRun={agentStatus?.latest_run}
                  backfillTimeline={backfillTimelineQuery.data}
                  isEditingBackfillTimeline={isEditingBackfillTimeline}
                  backfillTimelineDraft={backfillTimelineDraft}
                  backfillTimelineSaveMessage={backfillTimelineSaveMessage}
                  backfillTimelineSaveError={
                    backfillTimelineMutation.error instanceof Error
                      ? backfillTimelineMutation.error.message
                      : null
                  }
                  isSavingBackfillTimeline={backfillTimelineMutation.isPending}
                  onStartEditBackfillTimeline={() => {
                    const source = backfillTimelineQuery.data;
                    setBackfillTimelineDraft({
                      oldest_date_in_window:
                        source?.oldest_date_in_window ?? runtimeQueue?.checkpoint.window_start_date ?? "",
                      newest_boundary_exclusive:
                        source?.newest_boundary_exclusive ?? runtimeQueue?.checkpoint.created_before_boundary ?? "",
                    });
                    setBackfillTimelineSaveMessage(null);
                    setIsEditingBackfillTimeline(true);
                  }}
                  onCancelEditBackfillTimeline={() => {
                    setIsEditingBackfillTimeline(false);
                    setBackfillTimelineDraft({
                      oldest_date_in_window:
                        backfillTimelineQuery.data?.oldest_date_in_window ?? runtimeQueue?.checkpoint.window_start_date ?? "",
                      newest_boundary_exclusive:
                        backfillTimelineQuery.data?.newest_boundary_exclusive ?? runtimeQueue?.checkpoint.created_before_boundary ?? "",
                    });
                  }}
                  onChangeBackfillTimeline={(key, value) => {
                    setBackfillTimelineSaveMessage(null);
                    setBackfillTimelineDraft((current) => ({ ...current, [key]: value }));
                  }}
                  onSaveBackfillTimeline={() => backfillTimelineMutation.mutate(backfillTimelineDraft)}
                />
                <MetadataPanels entry={agentStatus} />
              </>
            ) : null}

            {selectedAgent === "backfill" ? (
              <>
                <RuntimeQueuePanels
                  agentId={selectedAgent}
                  queue={runtimeQueue}
                  latestRun={agentStatus?.latest_run}
                  backfillTimeline={undefined}
                  isEditingBackfillTimeline={false}
                  backfillTimelineDraft={{ oldest_date_in_window: "", newest_boundary_exclusive: "" }}
                  backfillTimelineSaveMessage={null}
                  backfillTimelineSaveError={null}
                  isSavingBackfillTimeline={false}
                  onStartEditBackfillTimeline={() => {}}
                  onCancelEditBackfillTimeline={() => {}}
                  onChangeBackfillTimeline={() => {}}
                  onSaveBackfillTimeline={() => {}}
                />
                <MetadataPanels entry={agentStatus} />
              </>
            ) : null}

            {selectedAgent === "analyst" ? <AnalystPanels entry={agentStatus} /> : null}

            {selectedAgent !== "firehose" &&
            selectedAgent !== "backfill" &&
            selectedAgent !== "analyst" ? (
              <MetadataPanels entry={agentStatus} />
            ) : null}

            {gatewayRuntimeQuery.error instanceof Error ? (
              <div className="card" style={{ borderColor: "rgba(217, 79, 79, 0.28)", background: "var(--red-dim)" }}>
                <p className="card-label" style={{ color: "var(--red)" }}>
                  Runtime surface issue
                </p>
                <p style={{ marginTop: "8px", color: "var(--text-1)" }}>
                  {gatewayRuntimeQuery.error.message}
                </p>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </>
  );
}

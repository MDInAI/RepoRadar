"use client";

import type { AgentName, AgentRunEvent, AgentRuntimeProgress } from "@/api/agents";
import type { SettingsSummaryResponse } from "@/lib/settings-contract";

export type OverviewCadenceSummary = {
  mode: "interval" | "queue" | "manual";
  stateLabel: string;
  whyWaiting: string;
  nextDueAt: string | null;
  remainingSeconds: number | null;
  intervalSeconds: number | null;
};

function toValidTimestamp(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? null : parsed;
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

export function formatCadenceDuration(seconds: number | null | undefined): string {
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

export function formatCadenceCountdown(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown";
  }
  const diffSeconds = Math.round((parsed.getTime() - Date.now()) / 1000);
  if (diffSeconds > 0) {
    return `In ${formatCadenceDuration(diffSeconds)}`;
  }
  if (diffSeconds === 0) {
    return "Due now";
  }
  return `Overdue by ${formatCadenceDuration(Math.abs(diffSeconds))}`;
}

export function deriveAgentCadenceSummary({
  agentId,
  isPaused,
  pauseReason,
  runtimeProgress,
  latestRun,
  settingsSummary,
}: {
  agentId: AgentName;
  isPaused: boolean;
  pauseReason: string | null | undefined;
  runtimeProgress: AgentRuntimeProgress | null | undefined;
  latestRun: AgentRunEvent | null | undefined;
  settingsSummary: SettingsSummaryResponse | undefined;
}): OverviewCadenceSummary {
  const lastCheckpointAt =
    runtimeProgress?.updated_at ?? latestRun?.completed_at ?? latestRun?.started_at ?? null;

  if (agentId === "firehose" || agentId === "backfill") {
    const intervalSeconds = findNumericSetting(settingsSummary, [
      agentId === "firehose" ? "workers.FIREHOSE_INTERVAL_SECONDS" : "workers.BACKFILL_INTERVAL_SECONDS",
      agentId === "firehose" ? "FIREHOSE_INTERVAL_SECONDS" : "BACKFILL_INTERVAL_SECONDS",
    ]);

    const checkpointTimeMs = toValidTimestamp(lastCheckpointAt);
    let nextDueAt: string | null = null;
    let remainingSeconds: number | null = null;

    if (intervalSeconds != null && checkpointTimeMs != null) {
      const elapsedSeconds = Math.max(0, (Date.now() - checkpointTimeMs) / 1000);
      remainingSeconds = Math.max(0, intervalSeconds - elapsedSeconds);
      nextDueAt = new Date(checkpointTimeMs + intervalSeconds * 1000).toISOString();
    }

    if (isPaused) {
      return {
        mode: "interval",
        stateLabel: "Paused",
        whyWaiting: pauseReason ?? "Automatic runs are blocked until you resume this agent.",
        nextDueAt,
        remainingSeconds,
        intervalSeconds,
      };
    }

    if (intervalSeconds == null) {
      return {
        mode: "interval",
        stateLabel: "Cadence unknown",
        whyWaiting: "The app cannot currently resolve the worker interval settings for this agent.",
        nextDueAt: null,
        remainingSeconds: null,
        intervalSeconds: null,
      };
    }

    if ((remainingSeconds ?? 0) <= 0) {
      return {
        mode: "interval",
        stateLabel: "Due now",
        whyWaiting: "The scheduled time has arrived. This agent is eligible to start on the next scheduler pass or manual run.",
        nextDueAt,
        remainingSeconds: 0,
        intervalSeconds,
      };
    }

    return {
      mode: "interval",
      stateLabel: "Waiting for schedule",
      whyWaiting: `This agent is cooling down until its ${formatCadenceDuration(intervalSeconds)} cadence finishes.`,
      nextDueAt,
      remainingSeconds,
      intervalSeconds,
    };
  }

  if (agentId === "bouncer" || agentId === "analyst") {
    return {
      mode: "queue",
      stateLabel: isPaused ? "Paused" : "Queue-driven",
      whyWaiting: isPaused
        ? (pauseReason ?? "This agent is paused until you resume it.")
        : agentId === "bouncer"
          ? "This agent starts when repositories are waiting for triage."
          : "This agent starts when accepted repositories are waiting for analysis.",
      nextDueAt: null,
      remainingSeconds: null,
      intervalSeconds: null,
    };
  }

  return {
    mode: "manual",
    stateLabel: isPaused ? "Paused" : "Manual / on-demand",
    whyWaiting: isPaused
      ? (pauseReason ?? "This agent is paused until you resume it.")
      : "This agent does not currently run on a recurring schedule.",
    nextDueAt: null,
    remainingSeconds: null,
    intervalSeconds: null,
  };
}

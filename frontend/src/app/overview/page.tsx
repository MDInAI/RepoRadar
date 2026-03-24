"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { type ReactNode, useMemo, useState } from "react";

import {
  AGENT_DISPLAY_ORDER,
  fetchLatestAgentRuns,
  fetchAgentPauseStates,
  fetchFailureEvents,
  fetchSystemEvents,
  getLatestAgentRunsQueryKey,
  getAgentPauseStatesQueryKey,
  getFailureEventsQueryKey,
  getSystemEventsQueryKey,
  sortAgentStatusEntries,
  type AgentName,
  type AgentPauseState,
  type AgentStatusEntry,
  type FailureEventPayload,
} from "@/api/agents";
import {
  fetchOverviewSummary,
  getOverviewSummaryQueryKey,
  type OverviewSummary,
} from "@/api/overview";
import { fetchOverlordSummary, getOverlordSummaryQueryKey } from "@/api/overlord";
import { fetchGatewayRuntime, fetchSettingsSummary } from "@/api/readiness";
import { EventTimeline } from "@/components/agents/EventTimeline";
import { GitHubBudgetPanel } from "@/components/agents/GitHubBudgetPanel";
import { GeminiKeyPoolPanel } from "@/components/agents/GeminiKeyPoolPanel";
import { StatusBar } from "@/components/dashboard/StatusBar";
import { PipelineStrip } from "@/components/dashboard/PipelineStrip";
import {
  buildLatestActiveFailureByAgent,
  isAgentPausedEffectively,
  isAgentEffectivelyRunning,
} from "@/components/agents/alertState";
import {
  formatAgentName,
  formatItemsSummary,
  formatRelativeTimestamp,
  formatRuntimeProgressCounts,
  formatRuntimeProgressHeadline,
  formatRuntimeSecondaryCounts,
} from "@/components/agents/agentPresentation";
import { formatCadenceCountdown } from "@/components/agents/agentCadence";
import { useEventStream } from "@/hooks/useEventStream";
import type { GatewayAgentIntakeQueueSummary, GatewayAgentQueue } from "@/lib/gateway-contract";
import type { SettingsSummaryResponse } from "@/lib/settings-contract";
import { formatAppDateTime } from "@/lib/time";

/* ── Helpers ────────────────────────────────── */

function formatTokenCount(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return `${value}`;
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "unavailable";
  const rounded = Math.max(0, Math.round(seconds));
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const secs = rounded % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

function formatRetryWindow(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return "the provider retry window";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

const AGENT_FALLBACK_META: Record<
  AgentName,
  {
    displayName: string;
    roleLabel: string;
    description: string;
    runtimeKind: string;
    usesGitHubToken: boolean;
    usesModel: boolean;
  }
> = {
  overlord: {
    displayName: "Overlord",
    roleLabel: "System coordination",
    description: "Monitors the operator posture and overall workflow health.",
    runtimeKind: "control-plane",
    usesGitHubToken: false,
    usesModel: false,
  },
  firehose: {
    displayName: "Firehose",
    roleLabel: "Repository intake",
    description: "Discovers repositories from fresh GitHub search feeds.",
    runtimeKind: "github-api-worker",
    usesGitHubToken: true,
    usesModel: false,
  },
  backfill: {
    displayName: "Backfill",
    roleLabel: "Historical intake",
    description: "Sweeps older GitHub windows to catch missed repositories.",
    runtimeKind: "github-api-worker",
    usesGitHubToken: true,
    usesModel: false,
  },
  bouncer: {
    displayName: "Bouncer",
    roleLabel: "Repository triage",
    description: "Applies triage rules to accepted and rejected repositories.",
    runtimeKind: "queue-worker",
    usesGitHubToken: false,
    usesModel: false,
  },
  analyst: {
    displayName: "Analyst",
    roleLabel: "README analysis",
    description: "Analyzes accepted repositories and stores structured findings.",
    runtimeKind: "queue-worker",
    usesGitHubToken: true,
    usesModel: true,
  },
  combiner: {
    displayName: "Combiner",
    roleLabel: "Synthesis",
    description: "Combines analyzed evidence into higher-level opportunities.",
    runtimeKind: "queue-worker",
    usesGitHubToken: false,
    usesModel: true,
  },
  obsession: {
    displayName: "Obsession",
    roleLabel: "Idea workspace",
    description: "Tracks persistent context and curated opportunity threads.",
    runtimeKind: "workspace",
    usesGitHubToken: false,
    usesModel: false,
  },
};

function buildFallbackAgentStatusEntry(agentName: AgentName): AgentStatusEntry {
  const meta = AGENT_FALLBACK_META[agentName];
  return {
    agent_name: agentName,
    display_name: meta.displayName,
    role_label: meta.roleLabel,
    description: meta.description,
    implementation_status: "unknown",
    runtime_kind: meta.runtimeKind,
    uses_github_token: meta.usesGitHubToken,
    uses_model: meta.usesModel,
    configured_provider: null,
    configured_model: null,
    notes: [],
    token_usage_24h: 0,
    input_tokens_24h: 0,
    output_tokens_24h: 0,
    has_run: false,
    latest_run: null,
    latest_intake_summary: null,
    runtime_progress: null,
  };
}

function buildOverviewAgentFleet(entries: AgentStatusEntry[]): AgentStatusEntry[] {
  const entryMap = new Map(entries.map((entry) => [entry.agent_name, entry]));
  return sortAgentStatusEntries(
    AGENT_DISPLAY_ORDER.map((agentName) => entryMap.get(agentName) ?? buildFallbackAgentStatusEntry(agentName)),
  );
}

function describeRecommendedAction(
  entry: AgentStatusEntry,
  pauseState: AgentPauseState | undefined,
  failureEvent: FailureEventPayload | undefined,
): string {
  if (pauseState?.is_paused) {
    if (failureEvent?.failure_classification === "rate_limited" && failureEvent.upstream_provider === "github") {
      if (failureEvent.retry_after_seconds != null && failureEvent.retry_after_seconds > 0) {
        return `Wait ${formatRetryWindow(failureEvent.retry_after_seconds)}, then resume from Control.`;
      }
      return "Wait for GitHub cooldown, then resume from Control.";
    }
    return "Review pause reason, then resume from Control.";
  }
  if (isAgentEffectivelyRunning(entry, pauseState)) return "No action needed — watch progress.";
  if (
    entry.latest_run?.status === "failed" &&
    (failureEvent?.failure_classification === "retryable" || failureEvent?.failure_classification === "rate_limited")
  ) {
    if (failureEvent.retry_after_seconds != null && failureEvent.retry_after_seconds > 0) {
      return `Automatic retry after cooldown. No manual resume needed.`;
    }
    return "Automatic retry expected — no manual resume.";
  }
  if (entry.latest_run?.status === "failed") return "Review the alert, then rerun from Control.";
  return "Waiting for next workload — no action needed.";
}

function toValidTimestamp(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? null : parsed;
}

function formatExactTimestamp(value: string | null | undefined): string {
  return value ? formatAppDateTime(value) : "Unavailable";
}

function formatTimestampPair(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }
  return `${formatRelativeTimestamp(value)} (${formatAppDateTime(value)})`;
}

function formatRetryReadyAt(event: FailureEventPayload | undefined): string | null {
  if (!event?.retry_after_seconds || event.retry_after_seconds <= 0) {
    return null;
  }
  const createdAt = toValidTimestamp(event.created_at);
  if (createdAt == null) {
    return null;
  }
  return formatAppDateTime(new Date(createdAt + event.retry_after_seconds * 1000));
}

function isAutoResumedState(pauseState: AgentPauseState | undefined): boolean {
  return Boolean(
    pauseState?.resumed_by === "auto" &&
      pauseState.resumed_at &&
      !isAgentPausedEffectively(pauseState),
  );
}

function buildAutoResumeDetail(
  pauseState: AgentPauseState | undefined,
  failureEvent: FailureEventPayload | undefined,
): string {
  const resumedAtText = pauseState?.resumed_at
    ? `${formatRelativeTimestamp(pauseState.resumed_at)} (${formatExactTimestamp(pauseState.resumed_at)})`
    : "recently";

  if (failureEvent?.failure_classification === "retryable") {
    return `Automation already cleared the old protective pause ${resumedAtText}. The current failure is retryable, so no manual resume is needed.`;
  }

  if (failureEvent?.failure_classification === "rate_limited") {
    return `Automation already cleared the old protective pause ${resumedAtText}. Cooldown handling stays automatic, so no manual resume is needed.`;
  }

  return `Automation cleared the previous protective pause ${resumedAtText}. This agent is back on its normal automatic scheduling.`;
}

function buildRecoveredInsight(
  pauseState: AgentPauseState | undefined,
  failureEvent: FailureEventPayload | undefined,
): MonitorInsight | null {
  if (!isAutoResumedState(pauseState)) {
    return null;
  }

  return {
    label: "Recovered",
    value: "Auto-resumed",
    detail: buildAutoResumeDetail(pauseState, failureEvent),
    tone: "good",
  };
}

function isLiveIntakeQueue(queue: GatewayAgentQueue): queue is GatewayAgentIntakeQueueSummary {
  return queue.status === "live";
}

function findNumericSetting(
  summary: SettingsSummaryResponse | undefined,
  keys: readonly string[],
): number | null {
  if (!summary) {
    return null;
  }
  for (const key of keys) {
    const workerSetting = summary.worker_settings.find((entry) => entry.key === key);
    if (workerSetting?.value) {
      const parsed = Number(workerSetting.value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
    const projectSetting = summary.project_settings.find((entry) => entry.key === key);
    if (projectSetting?.value) {
      const parsed = Number(projectSetting.value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }
  return null;
}

type InsightTone = "default" | "good" | "warn" | "critical";

type OverviewCadenceInsight = {
  mode: "interval" | "queue" | "manual";
  stateLabel: string;
  explanation: string;
  intervalSeconds: number | null;
  remainingSeconds: number | null;
  nextDueAt: string | null;
  lastCheckpointAt: string | null;
  schedulerStatusLabel: string;
  schedulerStatusTone: "default" | "good" | "warn";
  schedulerStatusExplanation: string;
  lastSchedulerEvidenceAt: string | null;
};

type MonitorInsight = {
  label: string;
  value: string;
  detail: string;
  tone?: InsightTone;
};

const OVERVIEW_HIGHLIGHT_REGEX =
  /(Manual resume|Manual pause|Failed and paused|Rate-limited|Late auto-run|Auto pickup|Auto-run|Idle backlog|Blocking|Blocked|Overdue(?:\sby)?|Paused|Alert|Running now|Running|Cooldown|Queue-driven|\b\d[\d,]*(?:\.\d+)?(?:\s(?:repos|pages|items|runs?))?|\b\d+[hms]\b)/gi;

function getOverviewHighlightTone(token: string): "critical" | "warn" | "good" | "info" | "count" {
  const normalized = token.toLowerCase();
  if (/\d/.test(normalized)) {
    return "count";
  }
  if (
    normalized.includes("manual resume") ||
    normalized.includes("manual pause") ||
    normalized.includes("failed and paused") ||
    normalized.includes("rate-limited") ||
    normalized.includes("blocked") ||
    normalized.includes("blocking") ||
    normalized.includes("paused") ||
    normalized.includes("alert")
  ) {
    return "critical";
  }
  if (
    normalized.includes("overdue") ||
    normalized.includes("late auto-run") ||
    normalized.includes("idle backlog") ||
    normalized.includes("cooldown")
  ) {
    return "warn";
  }
  if (
    normalized.includes("auto-run") ||
    normalized.includes("auto pickup") ||
    normalized.includes("running")
  ) {
    return "good";
  }
  return "info";
}

function renderHighlightedOverviewText(text: string, options?: { strong?: boolean }): ReactNode {
  const matches = Array.from(text.matchAll(new RegExp(OVERVIEW_HIGHLIGHT_REGEX.source, OVERVIEW_HIGHLIGHT_REGEX.flags)));
  if (matches.length === 0) {
    return text;
  }

  const segments: ReactNode[] = [];
  let cursor = 0;
  for (const match of matches) {
    const matchText = match[0];
    const start = match.index ?? 0;
    if (start > cursor) {
      segments.push(text.slice(cursor, start));
    }
    segments.push(
      <span
        key={`${matchText}-${start}`}
        className={`overview-highlight overview-highlight-${getOverviewHighlightTone(matchText)} ${options?.strong ? "overview-highlight-strong" : ""}`.trim()}
      >
        {matchText}
      </span>,
    );
    cursor = start + matchText.length;
  }

  if (cursor < text.length) {
    segments.push(text.slice(cursor));
  }

  return segments;
}

function deriveOverviewCadenceInsight({
  agentId,
  isPaused,
  pauseReason,
  runtimeQueue,
  latestRun,
  settingsSummary,
}: {
  agentId: AgentStatusEntry["agent_name"];
  isPaused: boolean;
  pauseReason: string | null | undefined;
  runtimeQueue: GatewayAgentIntakeQueueSummary | null;
  latestRun: AgentStatusEntry["latest_run"] | null | undefined;
  settingsSummary: SettingsSummaryResponse | undefined;
}): OverviewCadenceInsight {
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
    const checkpointTimeMs = toValidTimestamp(lastCheckpointAt);
    const canResumeImmediately =
      runtimeQueue != null &&
      "resume_required" in runtimeQueue.checkpoint &&
      Boolean(runtimeQueue.checkpoint.resume_required);

    let remainingSeconds: number | null = null;
    let nextDueAt: string | null = null;

    if (intervalSeconds != null) {
      if (canResumeImmediately || checkpointTimeMs == null) {
        remainingSeconds = 0;
      } else {
        const elapsedSeconds = Math.max(0, (nowMs - checkpointTimeMs) / 1000);
        remainingSeconds = Math.max(0, intervalSeconds - elapsedSeconds);
        nextDueAt = new Date(checkpointTimeMs + intervalSeconds * 1000).toISOString();
      }
    }

    if (isPaused) {
      return {
        mode: "interval",
        stateLabel: "Paused by policy",
        explanation: pauseReason ?? "Automatic runs are blocked until you resume this agent.",
        intervalSeconds,
        remainingSeconds,
        nextDueAt,
        lastCheckpointAt,
        schedulerStatusLabel: nextDueAt ? "Schedule blocked by pause" : "Paused",
        schedulerStatusTone: "warn",
        schedulerStatusExplanation: nextDueAt
          ? "The clock schedule still exists, but pause prevents that due run from starting automatically."
          : "Automatic runs are blocked while this pause remains active.",
        lastSchedulerEvidenceAt,
      };
    }

    if (canResumeImmediately) {
      return {
        mode: "interval",
        stateLabel: "Ready to resume",
        explanation: "The checkpoint is asking to continue immediately on the next eligible scheduler pass.",
        intervalSeconds,
        remainingSeconds: 0,
        nextDueAt: lastCheckpointAt,
        lastCheckpointAt,
        schedulerStatusLabel: "Resume requested",
        schedulerStatusTone: "good",
        schedulerStatusExplanation:
          "No cooldown is left. If the worker loop is healthy, this agent should continue by itself on the next scheduler pass.",
        lastSchedulerEvidenceAt,
      };
    }

    if (intervalSeconds == null) {
      return {
        mode: "interval",
        stateLabel: "Cadence unknown",
        explanation: "The dashboard could not resolve the live interval setting for this agent.",
        intervalSeconds: null,
        remainingSeconds: null,
        nextDueAt: null,
        lastCheckpointAt,
        schedulerStatusLabel: "Unavailable",
        schedulerStatusTone: "warn",
        schedulerStatusExplanation:
          "The interval setting is missing or unreadable, so the dashboard cannot say when this agent should auto-run next.",
        lastSchedulerEvidenceAt,
      };
    }

    if ((remainingSeconds ?? 0) <= 0) {
      const overdueSeconds = nextDueAt ? Math.max(0, Math.round((Date.now() - new Date(nextDueAt).getTime()) / 1000)) : 0;

      if (overdueSeconds > intervalSeconds) {
        return {
          mode: "interval",
          stateLabel: "Ready now",
          explanation: `The ${agentId} cooldown has already finished.`,
          intervalSeconds,
          remainingSeconds: 0,
          nextDueAt,
          lastCheckpointAt,
          schedulerStatusLabel: "Scheduler may be offline",
          schedulerStatusTone: "warn",
          schedulerStatusExplanation:
            "This run is late by more than one full interval. That usually means the scheduler loop is not currently picking work up.",
          lastSchedulerEvidenceAt,
        };
      }

      if (overdueSeconds > 300) {
        return {
          mode: "interval",
          stateLabel: "Ready now",
          explanation: `The ${agentId} cooldown has already finished.`,
          intervalSeconds,
          remainingSeconds: 0,
          nextDueAt,
          lastCheckpointAt,
          schedulerStatusLabel: "Overdue",
          schedulerStatusTone: "warn",
          schedulerStatusExplanation:
            "The scheduled time passed a while ago. The agent is eligible to auto-run, but the scheduler has not picked it up yet.",
          lastSchedulerEvidenceAt,
        };
      }

      if (overdueSeconds > 0) {
        return {
          mode: "interval",
          stateLabel: "Ready now",
          explanation: `The ${agentId} cooldown has already finished.`,
          intervalSeconds,
          remainingSeconds: 0,
          nextDueAt,
          lastCheckpointAt,
          schedulerStatusLabel: "Awaiting scheduler pickup",
          schedulerStatusTone: "default",
          schedulerStatusExplanation:
            "The scheduled time just passed. This usually means the worker loop has not hit its next poll yet.",
          lastSchedulerEvidenceAt,
        };
      }

      return {
        mode: "interval",
        stateLabel: "Ready now",
        explanation: `The ${agentId} cooldown has already finished.`,
        intervalSeconds,
        remainingSeconds: 0,
        nextDueAt,
        lastCheckpointAt,
        schedulerStatusLabel: "Due now",
        schedulerStatusTone: "good",
        schedulerStatusExplanation:
          "The next scheduled run is due now. If the worker loop is healthy, it should start automatically without manual help.",
        lastSchedulerEvidenceAt,
      };
    }

    return {
      mode: "interval",
      stateLabel: "Waiting on interval",
      explanation: `This agent is cooling down until its ${formatDuration(intervalSeconds)} cadence finishes.`,
      intervalSeconds,
      remainingSeconds,
      nextDueAt,
      lastCheckpointAt,
      schedulerStatusLabel: "On schedule",
      schedulerStatusTone: "good",
      schedulerStatusExplanation:
        "Nothing is wrong right now. The agent is between scheduled runs and is not expected to start again yet.",
      lastSchedulerEvidenceAt,
    };
  }

  if (agentId === "bouncer" || agentId === "analyst") {
    return {
      mode: "queue",
      stateLabel: isPaused ? "Paused" : "Queue-driven",
      explanation: isPaused
        ? pauseReason ?? "Queue pickup is blocked until you resume this agent."
        : agentId === "bouncer"
          ? "This agent wakes up when repositories are waiting for triage."
          : "This agent wakes up when accepted repositories are waiting for analysis.",
      intervalSeconds: null,
      remainingSeconds: null,
      nextDueAt: null,
      lastCheckpointAt,
      schedulerStatusLabel: isPaused ? "Paused" : "Queue-driven",
      schedulerStatusTone: isPaused ? "warn" : "default",
      schedulerStatusExplanation: isPaused
        ? "Automatic queue pickup is blocked while this pause is active."
        : "There is no clock schedule here. This worker starts when queue work appears and the worker loop is healthy.",
      lastSchedulerEvidenceAt,
    };
  }

  return {
    mode: "manual",
    stateLabel: isPaused ? "Paused" : "Manual / on-demand",
    explanation: isPaused ? pauseReason ?? "This agent is paused until resumed." : "This agent does not run on a recurring schedule.",
    intervalSeconds: null,
    remainingSeconds: null,
    nextDueAt: null,
    lastCheckpointAt,
    schedulerStatusLabel: isPaused ? "Paused" : "Manual trigger only",
    schedulerStatusTone: isPaused ? "warn" : "default",
    schedulerStatusExplanation: isPaused
      ? "Automatic work is blocked while this pause is active."
      : "This agent only runs when another workflow or operator explicitly triggers it.",
    lastSchedulerEvidenceAt,
  };
}

function getConnectionBadgeClassName(state: "connecting" | "open" | "closed" | "error"): string {
  if (state === "open") return "badge badge-green";
  if (state === "connecting") return "badge badge-yellow";
  if (state === "error") return "badge badge-red";
  return "badge badge-muted";
}

function getConnectionLabel(state: "connecting" | "open" | "closed" | "error"): string {
  if (state === "open") return "Live";
  if (state === "connecting") return "Connecting…";
  if (state === "error") return "Reconnecting…";
  return "Stream paused";
}

type FleetSortMode = "attention" | "backlog" | "running";

function getBackfillDetail(entry: AgentStatusEntry, prefix: string): string | null {
  const detail = entry.runtime_progress?.details.find((item) => item.startsWith(prefix));
  return detail ? detail.slice(prefix.length).trim() : null;
}

function getBackfillResumeLabel(entry: AgentStatusEntry): string | null {
  return getBackfillDetail(entry, "Resume page:");
}

function getAgentRemainingWork(entry: AgentStatusEntry): number {
  const progress = entry.runtime_progress;
  if (!progress) {
    return 0;
  }
  if (progress.remaining_count != null) {
    return progress.remaining_count;
  }
  if (progress.total_count != null && progress.completed_count != null) {
    return Math.max(progress.total_count - progress.completed_count, 0);
  }
  if (progress.secondary_remaining_count != null) {
    return progress.secondary_remaining_count;
  }
  if (progress.secondary_total_count != null && progress.secondary_completed_count != null) {
    return Math.max(progress.secondary_total_count - progress.secondary_completed_count, 0);
  }
  return 0;
}

function getAgentAttentionRank(
  entry: AgentStatusEntry,
  pauseState: AgentPauseState | undefined,
  hasActiveFailure: boolean,
): number {
  if (isAgentPausedEffectively(pauseState)) {
    return 3;
  }
  if (hasActiveFailure || entry.latest_run?.status === "failed") {
    return 2;
  }
  if (isAgentEffectivelyRunning(entry, pauseState)) {
    return 1;
  }
  return 0;
}

function buildCurrentWorkLine(
  entry: AgentStatusEntry,
  pauseState: AgentPauseState | undefined,
): string {
  const target = entry.runtime_progress?.current_target;
  if (entry.agent_name === "analyst" && target) {
    return `Currently analyzing: ${target}`;
  }
  if (entry.agent_name === "backfill") {
    const windowLabel = getBackfillDetail(entry, "Current historical window:");
    const resumeLabel = getBackfillResumeLabel(entry);
    if (windowLabel && isAgentPausedEffectively(pauseState)) {
      return `Paused before resuming ${windowLabel}${resumeLabel ? ` at ${resumeLabel.toLowerCase()}` : ""}`;
    }
    if (windowLabel && isAgentEffectivelyRunning(entry, pauseState)) {
      return `Scanning historical window: ${windowLabel}${resumeLabel ? ` (${resumeLabel.toLowerCase()})` : ""}`;
    }
    if (windowLabel) {
      return `Waiting to resume historical window ${windowLabel}${resumeLabel ? ` at ${resumeLabel.toLowerCase()}` : ""}`;
    }
  }
  if ((entry.agent_name === "firehose" || entry.agent_name === "backfill") && target) {
    return `Current checkpoint: ${target}`;
  }
  return formatRuntimeProgressHeadline(entry.runtime_progress) || formatItemsSummary(entry.latest_run) || "No active runtime snapshot";
}

function buildPrimaryProgressLine(entry: AgentStatusEntry): string {
  const progress = entry.runtime_progress;
  if (!progress) {
    return "No live progress snapshot";
  }
  if (entry.agent_name === "analyst" && progress.completed_count != null && progress.total_count != null) {
    return `This Gemini refresh run: ${progress.completed_count.toLocaleString()} of ${progress.total_count.toLocaleString()} repos processed`;
  }
  if (entry.agent_name === "backfill" && progress.completed_count != null && progress.total_count != null) {
    return `This Backfill window: page ${progress.completed_count.toLocaleString()} of ${progress.total_count.toLocaleString()} completed`;
  }
  if (entry.agent_name === "firehose" && progress.completed_count != null && progress.total_count != null) {
    return `Current cycle: ${progress.completed_count.toLocaleString()} of ${progress.total_count.toLocaleString()} pages processed`;
  }
  return formatRuntimeProgressCounts(progress);
}

function buildSecondaryProgressLine(entry: AgentStatusEntry): string | null {
  const progress = entry.runtime_progress;
  if (!progress) {
    return null;
  }
  if (entry.agent_name === "analyst" && progress.secondary_completed_count != null && progress.secondary_total_count != null) {
    return `Across all accepted repos: ${progress.secondary_completed_count.toLocaleString()} of ${progress.secondary_total_count.toLocaleString()} currently have analysis saved`;
  }
  if (entry.agent_name === "backfill") {
    const discovered = getBackfillDetail(entry, "Backfill repos discovered so far:");
    const downstream = getBackfillDetail(entry, "Backfill repos still waiting downstream:");
    if (discovered && downstream) {
      return `${discovered} repos discovered by Backfill so far · ${downstream} still waiting downstream`;
    }
    if (discovered) {
      return `${discovered} repos discovered by Backfill so far`;
    }
  }
  return formatRuntimeSecondaryCounts(progress);
}

function buildRuntimeDetailLines(entry: AgentStatusEntry): string[] {
  if (!entry.runtime_progress?.details?.length) {
    return [];
  }
  if (entry.agent_name === "backfill") {
    return entry.runtime_progress.details.filter(
      (detail) =>
        detail.startsWith("Resume page:") ||
        detail.startsWith("Cursor inside current window:"),
    );
  }
  return entry.runtime_progress.details.slice(0, 2);
}

function buildCompactRuntimeStats(entry: AgentStatusEntry): string[] {
  const lines: string[] = [];
  const progressLine = buildPrimaryProgressLine(entry);
  const secondaryLine = buildSecondaryProgressLine(entry);
  const workState = buildAgentWorkState(entry, undefined);

  if (progressLine) {
    lines.push(progressLine);
  }
  if (workState.remainingLine && workState.remainingLine !== "Actively processing now" && workState.remainingLine !== "No active work right now") {
    lines.push(workState.remainingLine);
  }
  if (secondaryLine) {
    lines.push(secondaryLine);
  }
  if (
    entry.latest_run?.status === "completed" &&
    entry.latest_run.items_processed != null &&
    (entry.agent_name === "backfill" || entry.agent_name === "firehose" || entry.agent_name === "bouncer")
  ) {
    lines.push(`Last completed run: ${entry.latest_run.items_processed.toLocaleString()} repos processed`);
  }
  return lines;
}

function buildAgentWorkState(
  entry: AgentStatusEntry,
  pauseState: AgentPauseState | undefined,
): {
  badgeClass: string;
  badgeLabel: string;
  currentLine: string;
  progressLine: string;
  secondaryLine: string | null;
  remainingLine: string;
} {
  const running = isAgentEffectivelyRunning(entry, pauseState);
  const progressLine = buildPrimaryProgressLine(entry);
  const secondaryLine = buildSecondaryProgressLine(entry);
  const currentLine = buildCurrentWorkLine(entry, pauseState);

  if (isAgentPausedEffectively(pauseState)) {
    return {
      badgeClass: "badge badge-red",
      badgeLabel: "Paused",
      currentLine,
      progressLine,
      secondaryLine,
      remainingLine:
        entry.runtime_progress?.remaining_count != null
          ? entry.agent_name === "analyst"
            ? `${entry.runtime_progress.remaining_count.toLocaleString()} repos still waiting in this same refresh run`
            : entry.agent_name === "backfill"
              ? `${entry.runtime_progress.remaining_count.toLocaleString()} pages left before this Backfill window is finished`
            : `${entry.runtime_progress.remaining_count.toLocaleString()} remaining before this agent catches up`
          : "Waiting for manual resume",
    };
  }

  if (running) {
    return {
      badgeClass: "badge badge-yellow",
      badgeLabel: "Running",
      currentLine,
      progressLine,
      secondaryLine,
      remainingLine:
        entry.runtime_progress?.remaining_count != null
          ? entry.agent_name === "analyst"
            ? `${entry.runtime_progress.remaining_count.toLocaleString()} repos still left in this current refresh run`
            : entry.agent_name === "backfill"
              ? `${entry.runtime_progress.remaining_count.toLocaleString()} pages left before this Backfill window is done`
            : `${entry.runtime_progress.remaining_count.toLocaleString()} remaining in the current workload`
          : "Actively processing now",
    };
  }

  if (entry.latest_run?.status === "failed") {
    return {
      badgeClass: "badge badge-red",
      badgeLabel: "Failed",
      currentLine,
      progressLine,
      secondaryLine,
      remainingLine: "Blocked until the failure is reviewed or retried",
    };
  }

  return {
    badgeClass: "badge badge-green",
    badgeLabel: "Waiting",
    currentLine,
    progressLine,
    secondaryLine,
    remainingLine:
      entry.runtime_progress?.remaining_count != null
        ? entry.agent_name === "analyst"
          ? `${entry.runtime_progress.remaining_count.toLocaleString()} repos still queued for Analyst`
          : entry.agent_name === "backfill"
            ? `${entry.runtime_progress.remaining_count.toLocaleString()} pages left before this Backfill window starts moving older again`
            : `${entry.runtime_progress.remaining_count.toLocaleString()} still queued for this agent`
        : "No active work right now",
  };
}

function buildStateInsight({
  entry,
  pauseState,
  failureEvent,
  cadence,
}: {
  entry: AgentStatusEntry;
  pauseState: AgentPauseState | undefined;
  failureEvent: FailureEventPayload | undefined;
  cadence: OverviewCadenceInsight;
}): MonitorInsight {
  const manuallyPaused = Boolean(
    isAgentPausedEffectively(pauseState) &&
    !failureEvent &&
    pauseState?.triggered_by_event_id == null,
  );
  const autoResumed = isAutoResumedState(pauseState);
  const errorSummary = entry.latest_run?.error_summary ?? failureEvent?.message ?? null;

  if (manuallyPaused) {
      return {
        label: "Why It Stopped",
        value: "Manual pause",
        detail: pauseState?.pause_reason
          ? `${pauseState.pause_reason}. Auto-runs stay blocked until you resume it.`
          : "This agent was paused manually. Auto-runs stay blocked until you resume it.",
        tone: "critical",
    };
  }

  if (isAgentPausedEffectively(pauseState)) {
    if (failureEvent?.failure_classification === "rate_limited") {
      return {
        label: "Why It Stopped",
        value: "Rate-limited",
        detail: `${pauseState?.pause_reason ?? failureEvent.message}. A protective pause is active, so the agent is no longer trying by itself.`,
        tone: "critical",
      };
    }
    return {
      label: "Why It Stopped",
      value: "Failed and paused",
      detail: pauseState?.pause_reason
        ? `${pauseState.pause_reason}. The run stopped and the agent is now waiting for operator review.`
        : "A protective pause is active after a failure, so this agent is waiting for operator review.",
      tone: "critical",
    };
  }

  if (autoResumed && entry.latest_run?.status === "failed" && failureEvent?.failure_classification === "retryable") {
    return {
      label: "Recovery",
      value: "Auto-resumed / retrying",
      detail: buildAutoResumeDetail(pauseState, failureEvent),
      tone: "good",
    };
  }

  if (autoResumed && entry.latest_run?.status === "failed" && failureEvent?.failure_classification === "rate_limited") {
    return {
      label: "Recovery",
      value: "Auto-resumed / cooling down",
      detail: buildAutoResumeDetail(pauseState, failureEvent),
      tone: "good",
    };
  }

  if (autoResumed && !failureEvent) {
    return {
      label: "Recovery",
      value: "Auto-resumed",
      detail: buildAutoResumeDetail(pauseState, failureEvent),
      tone: "good",
    };
  }

  if (entry.latest_run?.status === "failed") {
    if (failureEvent?.failure_classification === "retryable") {
      return {
        label: "Why It Stopped",
        value: "Retryable failure",
        detail: errorSummary
          ? `${errorSummary}. The agent is not paused and should retry automatically.`
          : "The last run failed with a retryable error. The agent is not paused and should retry automatically.",
        tone: "warn",
      };
    }
    if (failureEvent?.failure_classification === "rate_limited") {
      return {
        label: "Why It Stopped",
        value: "Cooling down",
        detail: errorSummary
          ? `${errorSummary}. The agent is waiting for its cooldown window and should retry automatically.`
          : "The last run hit a rate limit. The agent is waiting for its cooldown window and should retry automatically.",
        tone: "warn",
      };
    }
    return {
      label: "Why It Stopped",
      value: "Last run failed",
      detail: errorSummary
        ? `${errorSummary}. The agent is not paused, but it still needs attention before the next run.`
        : "The last run failed and still needs attention before the next run.",
      tone: "warn",
    };
  }

  if (isAgentEffectivelyRunning(entry, pauseState)) {
    return {
      label: "Why It Looks Active",
      value: "Running now",
      detail: buildCurrentWorkLine(entry, pauseState),
      tone: "good",
    };
  }

  if (cadence.mode === "interval" && (cadence.remainingSeconds ?? 0) > 0) {
    return {
      label: "Why It Is Waiting",
      value: "Cooldown",
      detail: cadence.explanation,
      tone: "default",
    };
  }

  if (cadence.mode === "queue" && getAgentRemainingWork(entry) > 0) {
    return {
      label: "Why It Is Waiting",
      value: "Idle backlog",
      detail: "Work is still waiting, so the worker loop should pick it up when the queue consumer is healthy.",
      tone: "warn",
    };
  }

  return {
    label: "Why It Is Waiting",
    value: "Waiting",
    detail: cadence.explanation,
    tone: "default",
  };
}

function buildResumeInsight({
  entry,
  pauseState,
  failureEvent,
  cadence,
}: {
  entry: AgentStatusEntry;
  pauseState: AgentPauseState | undefined;
  failureEvent: FailureEventPayload | undefined;
  cadence: OverviewCadenceInsight;
}): MonitorInsight {
  const retryReadyAt = formatRetryReadyAt(failureEvent);
  const autoResumed = isAutoResumedState(pauseState);

  if (isAgentPausedEffectively(pauseState)) {
    if (failureEvent?.failure_classification === "rate_limited") {
      return {
        label: "Will It Resume Itself?",
        value: "Manual resume",
        detail: retryReadyAt
          ? `Wait until about ${retryReadyAt}, then resume it manually. Pause blocks every automatic retry until you clear it.`
          : `Wait for the cooldown window to expire, then resume it manually. Pause blocks every automatic retry until you clear it.`,
        tone: "critical",
      };
    }

    return {
      label: "Will It Resume Itself?",
      value: "Manual resume",
      detail: pauseState?.resume_condition
        ? `${pauseState.resume_condition}. Even after that condition is true, the current pause still needs a manual resume from Control.`
        : "This pause will not clear on its own. You need to resume it manually from Control.",
      tone: "critical",
    };
  }

  if (
    autoResumed &&
    (failureEvent?.failure_classification === "retryable" || failureEvent?.failure_classification === "rate_limited")
  ) {
    return {
      label: "Will It Resume Itself?",
      value: "Already auto-resumed",
      detail: buildAutoResumeDetail(pauseState, failureEvent),
      tone: "good",
    };
  }

  if (autoResumed) {
    return {
      label: "Will It Resume Itself?",
      value: "Already recovered",
      detail: buildAutoResumeDetail(pauseState, failureEvent),
      tone: "good",
    };
  }

  if (cadence.mode === "interval") {
    if (entry.latest_run?.status === "failed" && failureEvent?.failure_classification === "retryable") {
      return {
        label: "Will It Resume Itself?",
        value: "Auto retry",
        detail: cadence.nextDueAt
          ? `No manual resume is needed. The next scheduled run should retry this automatically at ${formatExactTimestamp(cadence.nextDueAt)}.`
          : "No manual resume is needed. The next scheduled run should retry this automatically.",
        tone: "good",
      };
    }
    if (entry.latest_run?.status === "failed" && failureEvent?.failure_classification === "rate_limited") {
      return {
        label: "Will It Resume Itself?",
        value: "Auto retry",
        detail: retryReadyAt
          ? `No manual resume is needed. The worker should retry after the cooldown window ends around ${retryReadyAt}.`
          : "No manual resume is needed. The worker should retry automatically after the cooldown window ends.",
        tone: "good",
      };
    }
    if ((cadence.remainingSeconds ?? 0) > 0 && cadence.nextDueAt) {
      return {
        label: "Will It Resume Itself?",
        value: "Auto-run",
        detail: `No manual action is needed. The next scheduled slot is ${formatCadenceCountdown(cadence.nextDueAt).toLowerCase()} at ${formatExactTimestamp(cadence.nextDueAt)}.`,
        tone: "good",
      };
    }
    if (cadence.schedulerStatusTone === "warn") {
      return {
        label: "Will It Resume Itself?",
        value: "Late auto-run",
        detail: `${cadence.schedulerStatusExplanation} No manual resume is required, but the scheduler may need attention if this keeps slipping.`,
        tone: "warn",
      };
    }
    return {
      label: "Will It Resume Itself?",
      value: "Auto-run",
      detail: cadence.schedulerStatusExplanation,
      tone: "good",
    };
  }

  if (cadence.mode === "queue") {
    if (
      entry.latest_run?.status === "failed" &&
      (failureEvent?.failure_classification === "retryable" || failureEvent?.failure_classification === "rate_limited")
    ) {
      return {
        label: "Will It Resume Itself?",
        value: "Auto retry",
        detail: "No manual resume is needed. This worker is not paused, so it should retry automatically when the queue loop picks work up again.",
        tone: "good",
      };
    }
    if (getAgentRemainingWork(entry) > 0) {
      return {
        label: "Will It Resume Itself?",
        value: "Auto pickup",
        detail: "No manual resume is required while the agent is not paused. The worker loop should pick the next queued item by itself.",
        tone: "good",
      };
    }
    return {
      label: "Will It Resume Itself?",
      value: "On new work",
      detail: "There is no clock schedule here. This agent starts when new queue work shows up and the worker loop is healthy.",
      tone: "default",
    };
  }

  return {
    label: "Will It Resume Itself?",
    value: "Manual only",
    detail: "This agent does not have a recurring scheduler loop on this page.",
    tone: "default",
  };
}

function buildScheduleInsight({
  pauseState,
  cadence,
}: {
  pauseState: AgentPauseState | undefined;
  cadence: OverviewCadenceInsight;
}): MonitorInsight {
  if (cadence.mode === "interval") {
    if (isAgentPausedEffectively(pauseState) && cadence.nextDueAt) {
      return {
        label: "Automatic Schedule",
        value: `${formatCadenceCountdown(cadence.nextDueAt)}`,
        detail: `The next scheduled slot is ${formatExactTimestamp(cadence.nextDueAt)}, but pause is blocking that automatic run.`,
        tone: "warn",
      };
    }

    if (isAgentPausedEffectively(pauseState)) {
      return {
        label: "Automatic Schedule",
        value: "Blocked",
        detail: "The schedule still exists, but the pause prevents the next automatic run from starting.",
        tone: "warn",
      };
    }

    return {
      label: "Automatic Schedule",
      value: cadence.nextDueAt ? formatCadenceCountdown(cadence.nextDueAt) : cadence.stateLabel,
      detail: cadence.nextDueAt
        ? `${cadence.schedulerStatusLabel}. ${cadence.schedulerStatusExplanation} Next slot: ${formatExactTimestamp(cadence.nextDueAt)}.`
        : cadence.schedulerStatusExplanation,
      tone: cadence.schedulerStatusTone === "warn" ? "warn" : cadence.schedulerStatusTone === "good" ? "good" : "default",
    };
  }

  if (cadence.mode === "queue") {
    return {
      label: "Automatic Schedule",
      value: isAgentPausedEffectively(pauseState) ? "Blocked" : "Queue-driven",
      detail: isAgentPausedEffectively(pauseState)
        ? "There is no timer to wait for here. The pause is the only thing preventing automatic queue pickup."
        : "There is no clock schedule. This agent wakes up when queue work is present.",
      tone: isAgentPausedEffectively(pauseState) ? "warn" : "default",
    };
  }

  return {
    label: "Automatic Schedule",
    value: isAgentPausedEffectively(pauseState) ? "Blocked" : "No schedule",
    detail: cadence.schedulerStatusExplanation,
    tone: isAgentPausedEffectively(pauseState) ? "warn" : "default",
  };
}

function buildBacklogInsight({
  entry,
  data,
  runtimeQueue,
}: {
  entry: AgentStatusEntry;
  data: OverviewSummary | undefined;
  runtimeQueue: GatewayAgentIntakeQueueSummary | null;
}): MonitorInsight {
  if (entry.agent_name === "firehose") {
    const pending = runtimeQueue?.pending_items ?? data?.ingestion.pending_intake ?? 0;
    return {
      label: "Work Remaining",
      value: `${pending.toLocaleString()} repos`,
      detail: buildSecondaryProgressLine(entry) ?? "This is the current shared intake backlog still waiting to move downstream.",
      tone: pending > 0 ? "warn" : "default",
    };
  }

  if (entry.agent_name === "backfill") {
    const downstream = getBackfillDetail(entry, "Backfill repos still waiting downstream:");
    const remainingPages = entry.runtime_progress?.remaining_count ?? 0;
    return {
      label: "Work Remaining",
      value: `${remainingPages.toLocaleString()} pages`,
      detail: downstream
        ? `${downstream} repositories discovered by Backfill are still waiting downstream.`
        : buildSecondaryProgressLine(entry) ?? "This reflects the unfinished portion of the current historical window.",
      tone: remainingPages > 0 ? "warn" : "default",
    };
  }

  if (entry.agent_name === "bouncer") {
    const pending = data?.triage.pending ?? 0;
    return {
      label: "Work Remaining",
      value: `${pending.toLocaleString()} repos`,
      detail: pending > 0
        ? "These repositories are still waiting for Bouncer decisions."
        : "There is no triage backlog right now.",
      tone: pending > 0 ? "warn" : "default",
    };
  }

  if (entry.agent_name === "analyst") {
    const totalRemaining = (data?.analysis.pending ?? 0) + (data?.analysis.in_progress ?? 0) + (data?.analysis.failed ?? 0);
    return {
      label: "Work Remaining",
      value: `${totalRemaining.toLocaleString()} repos`,
      detail: `${(data?.analysis.pending ?? 0).toLocaleString()} pending · ${(data?.analysis.in_progress ?? 0).toLocaleString()} in progress · ${(data?.analysis.failed ?? 0).toLocaleString()} failed awaiting retry`,
      tone: totalRemaining > 0 ? "warn" : "default",
    };
  }

  return {
    label: "Work Remaining",
    value: buildAgentWorkState(entry, undefined).remainingLine,
    detail: "This agent is not part of the recurring intake/triage/analysis queue.",
    tone: "default",
  };
}

function getFleetCardToneClass({
  pauseState,
  failureEvent,
  entry,
}: {
  pauseState: AgentPauseState | undefined;
  failureEvent: FailureEventPayload | undefined;
  entry: AgentStatusEntry;
}): string {
  if (isAgentPausedEffectively(pauseState)) {
    return "fleet-card-critical";
  }
  if (failureEvent || entry.latest_run?.status === "failed") {
    return "fleet-card-warning";
  }
  if (isAgentEffectivelyRunning(entry, pauseState)) {
    return "fleet-card-running";
  }
  return "";
}

function MonitorFact({ insight, compact = false }: { insight: MonitorInsight; compact?: boolean }) {
  const toneClass =
    insight.tone === "critical"
      ? "monitor-fact-critical"
      : insight.tone === "warn"
        ? "monitor-fact-warn"
        : insight.tone === "good"
          ? "monitor-fact-good"
          : "";

  return (
    <div className={`monitor-fact ${toneClass} ${compact ? "monitor-fact-compact" : ""}`.trim()}>
      <div className="monitor-fact-label">{insight.label}</div>
      <div className="monitor-fact-value">{renderHighlightedOverviewText(insight.value, { strong: true })}</div>
      {!compact ? <div className="monitor-fact-detail">{renderHighlightedOverviewText(insight.detail)}</div> : null}
    </div>
  );
}

/* ── Main page ──────────────────────────────── */

export default function DashboardPage() {
  const [recentFailureSince] = useState(() => {
    const now = new Date();
    now.setHours(now.getHours() - 24);
    return now.toISOString();
  });
  const [recentEventSince] = useState(() => {
    const now = new Date();
    now.setHours(now.getHours() - 6);
    return now.toISOString();
  });

  const [expandGitHub, setExpandGitHub] = useState(false);
  const [expandGemini, setExpandGemini] = useState(false);
  const [fleetSortMode, setFleetSortMode] = useState<FleetSortMode>("attention");

  const { connectionState } = useEventStream();

  /* queries */
  const overviewQuery = useQuery({
    queryKey: getOverviewSummaryQueryKey(),
    queryFn: fetchOverviewSummary,
    refetchInterval: 30_000,
  });
  const latestRunsQuery = useQuery({
    queryKey: getLatestAgentRunsQueryKey(),
    queryFn: fetchLatestAgentRuns,
    refetchInterval: 15_000,
  });
  const pauseStatesQuery = useQuery({
    queryKey: getAgentPauseStatesQueryKey(),
    queryFn: fetchAgentPauseStates,
    refetchInterval: 10_000,
  });
  const failureEventsQuery = useQuery({
    queryKey: getFailureEventsQueryKey({ since: recentFailureSince, limit: 12 }),
    queryFn: () => fetchFailureEvents({ since: recentFailureSince, limit: 12 }),
    refetchInterval: 10_000,
  });
  const eventsQuery = useQuery({
    queryKey: getSystemEventsQueryKey({ since: recentEventSince, limit: 25 }),
    queryFn: () => fetchSystemEvents({ since: recentEventSince, limit: 25 }),
    refetchInterval: 10_000,
  });
  const gatewayRuntimeQuery = useQuery({
    queryKey: ["gateway", "runtime"],
    queryFn: fetchGatewayRuntime,
    refetchInterval: 30_000,
  });
  const settingsSummaryQuery = useQuery({
    queryKey: ["settings", "summary"],
    queryFn: fetchSettingsSummary,
    refetchInterval: 30_000,
  });
  const overlordQuery = useQuery({
    queryKey: getOverlordSummaryQueryKey(),
    queryFn: fetchOverlordSummary,
    refetchInterval: 15_000,
  });

  /* derived */
  const data = overviewQuery.data;
  const agents = useMemo(
    () => buildOverviewAgentFleet(latestRunsQuery.data?.agents ?? []),
    [latestRunsQuery.data?.agents],
  );
  const pauseStates = pauseStatesQuery.data ?? [];
  const failureEvents = failureEventsQuery.data ?? [];
  const systemEvents = eventsQuery.data ?? [];
  const pauseMap = useMemo(
    () => new Map(pauseStates.map((s) => [s.agent_name, s])),
    [pauseStates],
  );
  const runtimeAgentMap = new Map(
    (gatewayRuntimeQuery.data?.runtime.agent_states ?? []).map((agent) => [agent.agent_key, agent]),
  );
  const activeFailureByAgent = buildLatestActiveFailureByAgent(failureEvents, agents, pauseStates);

  const runningAgents = agents.filter((e) => isAgentEffectivelyRunning(e, pauseMap.get(e.agent_name)));
  const attentionAgents = agents.filter((e) => {
    const pause = pauseMap.get(e.agent_name);
    return Boolean(isAgentPausedEffectively(pause) || activeFailureByAgent.has(e.agent_name) || e.latest_run?.status === "failed");
  });
  const idleAgents = agents.filter((e) => {
    if (attentionAgents.some((a) => a.agent_name === e.agent_name)) return false;
    if (runningAgents.some((a) => a.agent_name === e.agent_name)) return false;
    return true;
  });
  const workboardAgents = useMemo(() => {
    const ranked = [...agents];
    ranked.sort((left, right) => {
      const leftPause = pauseMap.get(left.agent_name);
      const rightPause = pauseMap.get(right.agent_name);
      const leftAttention = getAgentAttentionRank(left, leftPause, activeFailureByAgent.has(left.agent_name));
      const rightAttention = getAgentAttentionRank(right, rightPause, activeFailureByAgent.has(right.agent_name));
      const leftRemaining = getAgentRemainingWork(left);
      const rightRemaining = getAgentRemainingWork(right);
      const leftRunning = isAgentEffectivelyRunning(left, leftPause) ? 1 : 0;
      const rightRunning = isAgentEffectivelyRunning(right, rightPause) ? 1 : 0;

      if (fleetSortMode === "attention") {
        if (rightAttention !== leftAttention) return rightAttention - leftAttention;
        if (rightRemaining !== leftRemaining) return rightRemaining - leftRemaining;
      } else if (fleetSortMode === "backlog") {
        if (rightRemaining !== leftRemaining) return rightRemaining - leftRemaining;
        if (rightAttention !== leftAttention) return rightAttention - leftAttention;
      } else {
        if (rightRunning !== leftRunning) return rightRunning - leftRunning;
        if (rightRemaining !== leftRemaining) return rightRemaining - leftRemaining;
        if (rightAttention !== leftAttention) return rightAttention - leftAttention;
      }

      return formatAgentName(left.agent_name).localeCompare(formatAgentName(right.agent_name));
    });
    return ranked;
  }, [activeFailureByAgent, agents, fleetSortMode, pauseMap]);

  const loading = latestRunsQuery.isLoading && overviewQuery.isLoading;

  if (overviewQuery.error) {
    return (
      <>
        <div className="topbar">
          <span className="topbar-title">Dashboard</span>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: "20px" }}>
          <div className="card-critical">
            <div className="heading-t2" style={{ color: "var(--red)" }}>Failed to load dashboard</div>
            <div style={{ marginTop: "8px", color: "var(--text-2)" }}>Check that the backend API is running.</div>
          </div>
        </div>
      </>
    );
  }

  /* pipeline stages */
  const pipelineStages = [
    { name: "Firehose", agentName: "firehose" as const, count: data?.backlog.queue_pending ?? 0, label: "in queue" },
    { name: "Backfill", agentName: "backfill" as const, count: 0, label: "historical" },
    { name: "Bouncer", agentName: "bouncer" as const, count: data?.triage.pending ?? 0, label: "triage" },
    { name: "Analyst", agentName: "analyst" as const, count: data?.analysis.in_progress ?? 0, label: "analyzing" },
    { name: "Combiner", agentName: "combiner" as const, count: 0, label: "synthesis" },
    { name: "Ideas DB", agentName: null, count: data?.triage.accepted ?? 0, label: "accepted" },
  ];

  return (
    <>
      {/* ─── Topbar ─── */}
      <div className="topbar">
        <span className="topbar-title">Dashboard</span>
        <span className={getConnectionBadgeClassName(connectionState)}>{getConnectionLabel(connectionState)}</span>
      </div>

      <div className="overview-shell">
        {loading ? (
          <div style={{ color: "var(--text-3)" }}>Loading…</div>
        ) : (
          <div className="overview-stack">
            {/* ═══════ ZONE 1: STATUS BAR ═══════ */}
            <StatusBar
              githubBudget={gatewayRuntimeQuery.data?.runtime.github_api_budget}
              geminiKeyPool={gatewayRuntimeQuery.data?.runtime.gemini_api_key_pool}
              pauseStates={pauseStates}
              failureEvents={failureEvents}
              agentStatuses={agents}
              runningCount={runningAgents.length}
              readyCount={idleAgents.length}
              totalAgents={agents.length}
              queuePending={data?.analysis.pending ?? 0}
              onExpandGitHub={() => setExpandGitHub((v) => !v)}
              onExpandGemini={() => setExpandGemini((v) => !v)}
            />

            {/* Expandable detail panels */}
            {expandGitHub && (
              <div>
                <GitHubBudgetPanel snapshot={gatewayRuntimeQuery.data?.runtime.github_api_budget} title="GitHub API Budget — Full Detail" />
              </div>
            )}
            {expandGemini && (
              <div>
                <GeminiKeyPoolPanel snapshot={gatewayRuntimeQuery.data?.runtime.gemini_api_key_pool} title="Gemini Key Pool — Full Detail" />
              </div>
            )}

            {/* ═══════ ZONE 2: ATTENTION REQUIRED ═══════ */}
            {attentionAgents.length > 0 ? (
              <div className="zone zone-attention">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                  <div className="heading-t2" style={{ color: "var(--amber)" }}>
                    Attention Required
                  </div>
                  <Link className="btn btn-sm" href="/control">Open Control</Link>
                </div>
                <div style={{ display: "grid", gap: "10px" }}>
                  {attentionAgents.map((entry) => {
                    const pause = pauseMap.get(entry.agent_name);
                    const failure = activeFailureByAgent.get(entry.agent_name);
                    const recoveredInsight = buildRecoveredInsight(pause, failure);
                    const autoResumed = isAutoResumedState(pause);
                    const isPaused = isAgentPausedEffectively(pause);
                    const runtimeAgent = runtimeAgentMap.get(entry.agent_name);
                    const runtimeQueue = runtimeAgent && isLiveIntakeQueue(runtimeAgent.queue) ? runtimeAgent.queue : null;
                    const cadence = deriveOverviewCadenceInsight({
                      agentId: entry.agent_name,
                      isPaused,
                      pauseReason: pause?.pause_reason,
                      runtimeQueue,
                      latestRun: entry.latest_run,
                      settingsSummary: settingsSummaryQuery.data,
                    });
                    const stateInsight = buildStateInsight({
                      entry,
                      pauseState: pause,
                      failureEvent: failure,
                      cadence,
                    });
                    const resumeInsight = buildResumeInsight({
                      entry,
                      pauseState: pause,
                      failureEvent: failure,
                      cadence,
                    });
                    const scheduleInsight = buildScheduleInsight({
                      pauseState: pause,
                      cadence,
                    });
                    const backlogInsight = buildBacklogInsight({
                      entry,
                      data,
                      runtimeQueue,
                    });
                    const timestampInsight = recoveredInsight
                      ? recoveredInsight
                      : pause?.paused_at
                        ? {
                          label: "Paused",
                          value: formatRelativeTimestamp(pause.paused_at),
                          detail: formatExactTimestamp(pause.paused_at),
                          tone: "warn" as const,
                        }
                        : failure
                          ? {
                            label: "Alert",
                            value: formatRelativeTimestamp(failure.created_at),
                            detail: failure.message,
                            tone: "warn" as const,
                          }
                          : null;
                    const cardClass = isPaused ? "attention-card attention-card-critical" : "attention-card attention-card-warning";
                    return (
                      <div key={entry.agent_name} className={cardClass}>
                        <div className="attention-card-header">
                          <div>
                            <div className="attention-card-title">{formatAgentName(entry.agent_name)}</div>
                            <div style={{ fontSize: "11px", color: "var(--text-2)", marginTop: "2px" }}>{entry.role_label}</div>
                          </div>
                          <div style={{ display: "flex", gap: "6px" }}>
                            {isPaused && <span className="badge badge-red">Paused</span>}
                            {autoResumed && !isPaused && <span className="badge badge-blue">Auto-resumed</span>}
                            {failure && <span className="badge badge-yellow">Alert</span>}
                            {!isPaused && entry.latest_run?.status === "failed" && <span className="badge badge-red">Failed</span>}
                          </div>
                        </div>
                        <div className="attention-card-summaryline">
                          <span className="attention-card-summary-primary">{renderHighlightedOverviewText(stateInsight.value, { strong: true })}</span>
                          <span className="attention-card-summary-separator">•</span>
                          <span className="attention-card-summary-secondary">
                            {renderHighlightedOverviewText(
                              autoResumed
                                ? buildAutoResumeDetail(pause, failure)
                                : pause?.pause_reason ?? failure?.message ?? stateInsight.detail,
                            )}
                          </span>
                        </div>
                        <div className="attention-card-facts">
                          <MonitorFact insight={{ ...resumeInsight, label: "Resume" }} compact />
                          <MonitorFact insight={{ ...scheduleInsight, label: "Next Run" }} compact />
                          <MonitorFact insight={{ ...backlogInsight, label: "Remaining" }} compact />
                          {timestampInsight ? <MonitorFact insight={timestampInsight} compact /> : null}
                        </div>
                        <div className="attention-card-action">
                          {renderHighlightedOverviewText(describeRecommendedAction(entry, pause, failure), { strong: true })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="card-success" style={{ padding: "12px 16px" }}>
                <span style={{ color: "var(--green)", fontWeight: 600 }}>All clear</span>
                <span style={{ color: "var(--text-2)", marginLeft: "8px" }}>— No agents need attention right now.</span>
              </div>
            )}

            {/* ═══════ ZONE 3: PIPELINE & AGENTS ═══════ */}
            <div className="zone zone-pipeline">
              <div className="heading-t2" style={{ marginBottom: "14px" }}>Pipeline Status</div>
              <PipelineStrip
                stages={pipelineStages}
                agents={agents}
                pauseStates={pauseStates}
              />

              {/* Key metrics row */}
              <div className="overview-metrics-grid">
                <div className="card-info" style={{ textAlign: "center" }}>
                  <div className="heading-t3">Discovered 24h</div>
                  <div className="metric-primary" style={{ marginTop: "6px" }}>
                    {data?.ingestion.discovered_last_24h?.toLocaleString() ?? "—"}
                  </div>
                  <div style={{ fontSize: "11px", color: "var(--text-2)", marginTop: "4px" }}>
                    {data?.ingestion.firehose_discovered_last_24h ?? 0} firehose · {data?.ingestion.backfill_discovered_last_24h ?? 0} backfill
                  </div>
                </div>
                <div className="card-info" style={{ textAlign: "center" }}>
                  <div className="heading-t3">Awaiting Analysis</div>
                  <div className="metric-primary" style={{ marginTop: "6px", color: (data?.analysis.pending ?? 0) > 0 ? "var(--blue)" : "var(--text-0)" }}>
                    {data?.analysis.pending?.toLocaleString() ?? "—"}
                  </div>
                  <div style={{ fontSize: "11px", color: "var(--text-2)", marginTop: "4px" }}>
                    accepted repos waiting for analyst
                  </div>
                </div>
                <div className="card-info" style={{ textAlign: "center" }}>
                  <div className="heading-t3">Analyzed</div>
                  <div className="metric-primary" style={{ marginTop: "6px" }}>
                    {data?.analysis.completed?.toLocaleString() ?? "—"}
                  </div>
                  <div style={{ fontSize: "11px", color: "var(--text-2)", marginTop: "4px" }}>
                    {data?.triage.accepted ?? 0} accepted · {data?.triage.rejected ?? 0} rejected
                  </div>
                </div>
                <div className="card-info" style={{ textAlign: "center" }}>
                  <div className="heading-t3">Token Burn 24h</div>
                  <div className="metric-primary" style={{ marginTop: "6px" }}>
                    {formatTokenCount(data?.token_usage.total_tokens_24h ?? 0)}
                  </div>
                  <div style={{ fontSize: "11px", color: "var(--text-2)", marginTop: "4px" }}>
                    {data?.token_usage.llm_runs_24h ?? 0} LLM runs
                  </div>
                </div>
              </div>
            </div>

            <div className="zone zone-pipeline">
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "12px",
                  marginBottom: "14px",
                  flexWrap: "wrap",
                }}
              >
                <div className="heading-t2">Fleet Workboard</div>
                <div className="fleet-sortbar">
                  <button
                    type="button"
                    className={`fleet-sortbtn ${fleetSortMode === "attention" ? "active" : ""}`}
                    onClick={() => setFleetSortMode("attention")}
                  >
                    Needs Attention
                  </button>
                  <button
                    type="button"
                    className={`fleet-sortbtn ${fleetSortMode === "backlog" ? "active" : ""}`}
                    onClick={() => setFleetSortMode("backlog")}
                  >
                    Most Backlog
                  </button>
                  <button
                    type="button"
                    className={`fleet-sortbtn ${fleetSortMode === "running" ? "active" : ""}`}
                    onClick={() => setFleetSortMode("running")}
                  >
                    Running First
                  </button>
                </div>
              </div>
              <div className="fleet-board">
                {workboardAgents.map((entry) => {
                  const pause = pauseMap.get(entry.agent_name);
                  const failure = activeFailureByAgent.get(entry.agent_name);
                  const autoResumed = isAutoResumedState(pause);
                  const workState = buildAgentWorkState(entry, pause);
                  const detailLines = buildRuntimeDetailLines(entry);
                  const runtimeAgent = runtimeAgentMap.get(entry.agent_name);
                  const runtimeQueue = runtimeAgent && isLiveIntakeQueue(runtimeAgent.queue) ? runtimeAgent.queue : null;
                  const cadence = deriveOverviewCadenceInsight({
                    agentId: entry.agent_name,
                    isPaused: isAgentPausedEffectively(pause),
                    pauseReason: pause?.pause_reason,
                    runtimeQueue,
                    latestRun: entry.latest_run,
                    settingsSummary: settingsSummaryQuery.data,
                  });
                  const stateInsight = buildStateInsight({
                    entry,
                    pauseState: pause,
                    failureEvent: failure,
                    cadence,
                  });
                  const resumeInsight = buildResumeInsight({
                    entry,
                    pauseState: pause,
                    failureEvent: failure,
                    cadence,
                  });
                  const scheduleInsight = buildScheduleInsight({
                    pauseState: pause,
                    cadence,
                  });
                  const backlogInsight = buildBacklogInsight({
                    entry,
                    data,
                    runtimeQueue,
                  });
                  const cardToneClass = getFleetCardToneClass({
                    pauseState: pause,
                    failureEvent: failure,
                    entry,
                  });
                  return (
                    <section key={entry.agent_name} className={`fleet-card ${cardToneClass}`.trim()}>
                      <div className="fleet-card-header">
                        <div>
                          <div className="fleet-card-title">{formatAgentName(entry.agent_name)}</div>
                          <div className="fleet-card-subtitle">{entry.role_label}</div>
                        </div>
                        <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                          {autoResumed && !isAgentPausedEffectively(pause) ? <span className="badge badge-blue">Auto-resumed</span> : null}
                          <span className={workState.badgeClass}>{workState.badgeLabel}</span>
                        </div>
                      </div>

                      <div className="fleet-card-hero">
                        <div className="fleet-card-hero-title">{renderHighlightedOverviewText(workState.currentLine, { strong: true })}</div>
                        <div className="fleet-card-hero-subtitle">
                          {renderHighlightedOverviewText(
                            autoResumed
                              ? buildAutoResumeDetail(pause, failure)
                              : failure?.message ?? pause?.pause_reason ?? stateInsight.value,
                          )}
                        </div>
                      </div>

                      <div className="monitor-fact-grid">
                        <MonitorFact insight={{ ...stateInsight, label: "Status" }} compact />
                        <MonitorFact insight={{ ...resumeInsight, label: "Resume" }} compact />
                        <MonitorFact insight={{ ...scheduleInsight, label: "Next Run" }} compact />
                        <MonitorFact insight={{ ...backlogInsight, label: "Remaining" }} compact />
                      </div>

                      <div className="fleet-card-metrics">
                        <div className="fleet-card-stat">
                          <div className="card-label">Progress</div>
                          <div className="fleet-card-stat-value">{renderHighlightedOverviewText(workState.progressLine)}</div>
                        </div>
                        <div className="fleet-card-stat">
                          <div className="card-label">Current Run</div>
                          <div className="fleet-card-stat-value">{renderHighlightedOverviewText(workState.remainingLine)}</div>
                        </div>
                      </div>

                      <details className="fleet-card-details">
                        <summary>Show details</summary>
                        <div className="fleet-card-details-body">
                          <div className="fleet-card-detail-item">
                            <div className="fleet-card-detail-label">Why stopped</div>
                            <div className="fleet-card-detail-value">{stateInsight.detail}</div>
                          </div>
                          <div className="fleet-card-detail-item">
                            <div className="fleet-card-detail-label">Resume behavior</div>
                            <div className="fleet-card-detail-value">{resumeInsight.detail}</div>
                          </div>
                          <div className="fleet-card-detail-item">
                            <div className="fleet-card-detail-label">Schedule detail</div>
                            <div className="fleet-card-detail-value">{scheduleInsight.detail}</div>
                          </div>
                          {failure ? (
                            <div className="fleet-card-detail-item">
                              <div className="fleet-card-detail-label">Latest alert</div>
                              <div className="fleet-card-detail-value">
                                {failure.message}
                                {failure.retry_after_seconds != null && failure.retry_after_seconds > 0
                                  ? ` Retry window: wait about ${formatRetryWindow(failure.retry_after_seconds)} until ${formatRetryReadyAt(failure) ?? "the provider window ends"}.`
                                  : ""}
                              </div>
                            </div>
                          ) : null}
                          {isAgentPausedEffectively(pause) ? (
                            <div className="fleet-card-detail-item">
                              <div className="fleet-card-detail-label">Pause context</div>
                              <div className="fleet-card-detail-value">
                                {pause?.pause_reason ?? "Pause active, but no reason was recorded."}
                                {pause?.paused_at ? ` Paused ${formatTimestampPair(pause.paused_at)}.` : ""}
                                {pause?.resume_condition ? ` Resume condition: ${pause.resume_condition}.` : ""}
                              </div>
                            </div>
                          ) : null}
                          {workState.secondaryLine ? (
                            <div className="fleet-card-detail-item">
                              <div className="fleet-card-detail-label">Queue context</div>
                              <div className="fleet-card-detail-value">{workState.secondaryLine}</div>
                            </div>
                          ) : null}
                          {detailLines.length > 0 ? (
                            <div className="fleet-card-detail-item">
                              <div className="fleet-card-detail-label">
                                {entry.agent_name === "backfill" ? "Backfill snapshot" : "Runtime detail"}
                              </div>
                              <div className="fleet-card-detail-list">
                                {detailLines.map((detail) => (
                                  <div key={`${entry.agent_name}-${detail}`}>{detail}</div>
                                ))}
                              </div>
                            </div>
                          ) : null}
                          <div className="fleet-card-detail-item">
                            <div className="fleet-card-detail-label">Timestamps</div>
                            <div className="fleet-card-detail-list">
                              <div>Last checkpoint: {formatTimestampPair(cadence.lastCheckpointAt)}</div>
                              <div>Scheduler evidence: {formatTimestampPair(cadence.lastSchedulerEvidenceAt)}</div>
                              <div>
                                Last runtime update: {entry.runtime_progress?.updated_at ? formatTimestampPair(entry.runtime_progress.updated_at) : "Unavailable"}
                              </div>
                            </div>
                          </div>
                        </div>
                      </details>
                    </section>
                  );
                })}
              </div>
            </div>

            {/* ═══════ MAIN GRID: agents + sidebar ═══════ */}
            <div className="dashboard-grid">
              {/* Left column: Agent status */}
              <div>
                {/* Running now */}
                <div className="heading-t2" style={{ marginBottom: "10px" }}>Running Now</div>
                {runningAgents.length === 0 ? (
                  <div className="card-info" style={{ color: "var(--text-2)", marginBottom: "16px" }}>
                    No agents actively processing right now.
                  </div>
                ) : (
                  <div className="card-info" style={{ padding: 0, marginBottom: "16px" }}>
                    {runningAgents.map((entry) => {
                      const progress = formatRuntimeProgressHeadline(entry.runtime_progress) || formatItemsSummary(entry.latest_run);
                      const pct = entry.runtime_progress?.progress_percent;
                      const statLines = buildCompactRuntimeStats(entry);
                      const runtimeAgent = runtimeAgentMap.get(entry.agent_name);
                      const runtimeQueue = runtimeAgent && isLiveIntakeQueue(runtimeAgent.queue) ? runtimeAgent.queue : null;
                      const cadence = deriveOverviewCadenceInsight({
                        agentId: entry.agent_name,
                        isPaused: isAgentPausedEffectively(pauseMap.get(entry.agent_name)),
                        pauseReason: pauseMap.get(entry.agent_name)?.pause_reason,
                        runtimeQueue,
                        latestRun: entry.latest_run,
                        settingsSummary: settingsSummaryQuery.data,
                      });
                      return (
                        <div key={entry.agent_name} className="agent-row">
                          <div>
                            <div className="agent-row-name">{formatAgentName(entry.agent_name)}</div>
                            <div className="agent-row-role">{entry.role_label}</div>
                          </div>
                          <div>
                            <div className="agent-row-progress">{progress}</div>
                            {statLines.length > 0 ? (
                              <div style={{ marginTop: "4px", display: "grid", gap: "2px", fontSize: "11px", color: "var(--text-2)" }}>
                                {statLines.slice(0, 3).map((line) => (
                                  <div key={`${entry.agent_name}-${line}`}>{line}</div>
                                ))}
                              </div>
                            ) : null}
                            <div style={{ marginTop: "4px", fontSize: "11px", color: "var(--text-2)" }}>
                              {cadence.nextDueAt
                                ? `Next automatic run ${formatCadenceCountdown(cadence.nextDueAt).toLowerCase()}`
                                : cadence.mode === "queue"
                                  ? "Queue-driven: starts when work appears"
                                  : cadence.explanation}
                            </div>
                            {pct != null && (
                              <div className="progress" style={{ marginTop: "4px" }}>
                                <div className="progress-bar" style={{ width: `${Math.max(0, Math.min(pct, 100))}%`, background: "var(--amber)" }} />
                              </div>
                            )}
                          </div>
                          <span className="badge badge-yellow">Running</span>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Idle / ready */}
                <div className="heading-t2" style={{ marginBottom: "10px" }}>Ready & Idle</div>
                <div className="card-info" style={{ padding: 0, marginBottom: "16px" }}>
                  {idleAgents.length === 0 ? (
                    <div style={{ padding: "14px", color: "var(--text-2)" }}>No idle agents.</div>
                  ) : (
                    idleAgents.map((entry) => {
                      const progress = formatRuntimeProgressHeadline(entry.runtime_progress) || formatItemsSummary(entry.latest_run) || "—";
                      const statLines = buildCompactRuntimeStats(entry);
                      const runtimeAgent = runtimeAgentMap.get(entry.agent_name);
                      const runtimeQueue = runtimeAgent && isLiveIntakeQueue(runtimeAgent.queue) ? runtimeAgent.queue : null;
                      const cadence = deriveOverviewCadenceInsight({
                        agentId: entry.agent_name,
                        isPaused: isAgentPausedEffectively(pauseMap.get(entry.agent_name)),
                        pauseReason: pauseMap.get(entry.agent_name)?.pause_reason,
                        runtimeQueue,
                        latestRun: entry.latest_run,
                        settingsSummary: settingsSummaryQuery.data,
                      });
                      return (
                        <div key={entry.agent_name} className="agent-row">
                          <div>
                            <div className="agent-row-name">{formatAgentName(entry.agent_name)}</div>
                            <div className="agent-row-role">{entry.role_label}</div>
                          </div>
                          <div>
                            <div className="agent-row-progress">{progress}</div>
                            {statLines.length > 0 ? (
                              <div style={{ marginTop: "4px", display: "grid", gap: "2px", fontSize: "11px", color: "var(--text-2)" }}>
                                {statLines.slice(0, 2).map((line) => (
                                  <div key={`${entry.agent_name}-${line}`}>{line}</div>
                                ))}
                              </div>
                            ) : null}
                            <div style={{ marginTop: "4px", fontSize: "11px", color: "var(--text-2)" }}>
                              {cadence.nextDueAt
                                ? `Next automatic run ${formatCadenceCountdown(cadence.nextDueAt).toLowerCase()}`
                                : cadence.mode === "queue"
                                  ? cadence.explanation
                                  : cadence.mode === "manual"
                                    ? "No recurring schedule"
                                    : cadence.explanation}
                            </div>
                          </div>
                          <span className="badge badge-green">Idle</span>
                        </div>
                      );
                    })
                  )}
                </div>

                {/* Overlord summary */}
                {overlordQuery.data && (
                  <>
                    <div className="heading-t2" style={{ marginBottom: "10px" }}>Overlord</div>
                    <div className="card-info" style={{ marginBottom: "16px" }}>
                      <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-0)", marginBottom: "6px" }}>
                        {overlordQuery.data.headline}
                      </div>
                      <div style={{ fontSize: "12px", color: "var(--text-2)", marginBottom: "10px", lineHeight: 1.5 }}>
                        {overlordQuery.data.summary}
                      </div>
                      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                        <span className={`badge ${overlordQuery.data.incidents.length > 0 ? "badge-yellow" : "badge-green"}`}>
                          {overlordQuery.data.status}
                        </span>
                        <span className="badge badge-muted">{overlordQuery.data.incidents.length} incidents</span>
                        <span className="badge badge-muted">{overlordQuery.data.operator_todos.length} todos</span>
                      </div>
                      {overlordQuery.data.incidents.slice(0, 2).map((inc) => (
                        <div key={inc.incident_key} style={{ marginTop: "10px", paddingTop: "10px", borderTop: "1px solid var(--border)" }}>
                          <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-0)" }}>{inc.title}</div>
                          <div style={{ fontSize: "12px", color: "var(--text-2)", marginTop: "3px" }}>{inc.summary}</div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>

              {/* Right column: Activity feed + queue pressure */}
              <div>
                <div className="heading-t2" style={{ marginBottom: "10px" }}>Activity Feed</div>
                <div style={{ maxHeight: "500px", overflowY: "auto" }}>
                  <EventTimeline events={systemEvents} isLoading={eventsQuery.isLoading} />
                </div>

                <div className="heading-t2" style={{ marginTop: "16px", marginBottom: "10px" }}>Queue Pressure</div>
                <div className="card-info">
                  <div style={{ display: "grid", gap: "8px" }}>
                    {[
                      { label: "Intake Pending", value: data?.ingestion.pending_intake },
                      { label: "Triage Pending", value: data?.triage.pending },
                      { label: "Analysis Pending", value: data?.analysis.pending },
                      { label: "Analysis Failed", value: data?.analysis.failed },
                    ].map((row) => (
                      <div key={row.label} style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                        <span className="heading-t3">{row.label}</span>
                        <span style={{ color: "var(--text-0)", fontFamily: "var(--mono)", fontSize: "12px" }}>
                          {row.value?.toLocaleString() ?? "—"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="heading-t2" style={{ marginTop: "16px", marginBottom: "10px" }}>Quick Actions</div>
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  <Link className="btn" href="/control">Open Control Panel</Link>
                  <Link className="btn" href="/repositories">Browse Repositories</Link>
                  <Link className="btn" href="/ideas">Idea Workspace</Link>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

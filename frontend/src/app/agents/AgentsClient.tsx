"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  AGENT_DISPLAY_ORDER,
  fetchFailureEvents,
  fetchAgentPauseStates,
  fetchAgentRuns,
  fetchLatestAgentRuns,
  getFailureEventsQueryKey,
  getAgentPauseStatesQueryKey,
  getAgentRunsQueryKey,
  getLatestAgentRunsQueryKey,
  type AgentName,
  type AgentRunStatus,
  type AgentStatusEntry,
} from "@/api/agents";
import { fetchGatewayRuntime, fetchSettingsSummary } from "@/api/readiness";
import type {
  GatewayAgentIntakeQueueSummary,
  GatewayAgentQueue,
} from "@/lib/gateway-contract";
import type {
  MaskedSettingSummary,
  SettingsSummaryResponse,
} from "@/lib/settings-contract";
import { formatAppDateTime } from "@/lib/time";
import { AgentRunHistoryTable } from "@/components/agents/AgentRunHistoryTable";
import { GitHubBudgetPanel } from "@/components/agents/GitHubBudgetPanel";
import { AgentOperatorSummary } from "@/components/agents/AgentOperatorSummary";
import { OperationalAlertsPanel } from "@/components/agents/OperationalAlertsPanel";
import { PauseAgentButton } from "@/components/agents/PauseAgentButton";
import { ResumeAgentButton } from "@/components/agents/ResumeAgentButton";

const RUN_PAGE_SIZE = 50;
const MAX_RUN_PAGE_SIZE = 200;

type AgentCadence = {
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

function titleCase(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatTokenCount(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return `${value}`;
}

function formatTimestamp(value: string | null | undefined): string {
  return formatAppDateTime(value);
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
  if (diffMinutes < 1) return "Just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.round(diffHours / 24);
  return `${diffDays}d ago`;
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) {
    return "Unavailable";
  }
  const rounded = Math.max(0, Math.round(seconds));
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const secs = rounded % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
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
  if (diffSeconds > 0) return `In ${formatDuration(diffSeconds)}`;
  if (diffSeconds === 0) return "Due now";
  return `Overdue by ${formatDuration(Math.abs(diffSeconds))}`;
}

function toValidTimestamp(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? null : parsed;
}

function isLiveIntakeQueue(queue: GatewayAgentQueue): queue is GatewayAgentIntakeQueueSummary {
  return queue.status === "live";
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
    if (workerSetting?.value) return workerSetting.value;
    const projectSetting = summary.project_settings.find((entry) => entry.key === key);
    if (projectSetting?.value) return projectSetting.value;
  }
  return null;
}

function findNumericSetting(
  summary: SettingsSummaryResponse | undefined,
  keys: readonly string[],
): number | null {
  const value = findSettingValue(summary, keys);
  if (value == null) return null;
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
    if (workerSetting) return workerSetting;
    const projectSetting = summary.project_settings.find((entry) => entry.key === key);
    if (projectSetting) return projectSetting;
  }
  return null;
}

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
    let nextDueAt: string | null = null;

    if (intervalSeconds != null) {
      if (canResumeImmediately || checkpointTimeMs == null || Number.isNaN(checkpointTimeMs)) {
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
        explanation: pauseReason ?? "This cadence is blocked until an operator resumes the agent.",
        intervalSeconds,
        remainingSeconds,
        nextDueAt,
        lastCheckpointAt,
        schedulerStatusLabel: "Paused",
        schedulerStatusTone: "warn",
        schedulerStatusExplanation:
          "Automatic runs are blocked while this agent is paused, even if the scheduled time has already passed.",
        lastSchedulerEvidenceAt,
      };
    }

    if (intervalSeconds == null) {
      return {
        mode: "interval",
        stateLabel: "Cadence unavailable",
        explanation: "The runtime interval could not be resolved from live settings.",
        intervalSeconds: null,
        remainingSeconds: null,
        nextDueAt: null,
        lastCheckpointAt,
        schedulerStatusLabel: "Unavailable",
        schedulerStatusTone: "warn",
        schedulerStatusExplanation:
          "The page could not resolve the worker cadence, so scheduling health cannot be derived reliably.",
        lastSchedulerEvidenceAt,
      };
    }

    if ((remainingSeconds ?? 0) <= 0) {
      const overdueSeconds = nextDueAt ? Math.max(0, Math.round((Date.now() - new Date(nextDueAt).getTime()) / 1000)) : 0;
      let schedulerStatusLabel = "Due now";
      let schedulerStatusTone: "default" | "good" | "warn" = "good";
      let schedulerStatusExplanation =
        "The scheduled time has arrived. This agent should start on the next scheduler tick if the worker loop is alive.";

      if (overdueSeconds > 300 && overdueSeconds <= intervalSeconds) {
        schedulerStatusLabel = "Overdue";
        schedulerStatusTone = "warn";
        schedulerStatusExplanation =
          "The scheduled time passed and the agent still has not started. It is eligible to auto-run, but the scheduler may not be actively picking up jobs.";
      } else if (overdueSeconds > intervalSeconds) {
        schedulerStatusLabel = "Scheduler may be offline";
        schedulerStatusTone = "warn";
        schedulerStatusExplanation =
          "This run is overdue by more than one full interval. That usually means the scheduler loop is not currently active.";
      }

      return {
        mode: "interval",
        stateLabel: "Ready now",
        explanation: `The ${agentId} cadence has cooled down and can start on the next scheduler opportunity.`,
        intervalSeconds,
        remainingSeconds: 0,
        nextDueAt,
        lastCheckpointAt,
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
      schedulerStatusLabel: "On schedule",
      schedulerStatusTone: "good",
      schedulerStatusExplanation:
        "The cadence is still cooling down. This agent is not expected to start again until the scheduled time arrives.",
      lastSchedulerEvidenceAt,
    };
  }

  if (agentId === "bouncer" || agentId === "analyst") {
    const explanation =
      agentId === "analyst"
        ? "Analyst runs when accepted repositories are waiting for README analysis."
        : "Bouncer runs when pending repositories need triage.";
    return {
      mode: "queue",
      stateLabel: isPaused ? "Paused by policy" : "Queue-driven",
      explanation: isPaused ? (pauseReason ?? `${titleCase(agentId)} is paused until an operator resumes it.`) : explanation,
      intervalSeconds: null,
      remainingSeconds: null,
      nextDueAt: null,
      lastCheckpointAt,
      schedulerStatusLabel: isPaused ? "Paused" : "Queue-driven",
      schedulerStatusTone: isPaused ? "warn" : "default",
      schedulerStatusExplanation: isPaused
        ? "Automatic queue pickup is blocked while this agent is paused."
        : "This agent does not wait for a clock time. It runs whenever queue work is available and the worker loop is active.",
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
    schedulerStatusLabel: "Manual trigger only",
    schedulerStatusTone: "default",
    schedulerStatusExplanation:
      "This agent does not currently advertise a recurring scheduler loop on this surface.",
    lastSchedulerEvidenceAt,
  };
}

function StatusCard({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "good" | "warn" }) {
  const color = tone === "good" ? "var(--green)" : tone === "warn" ? "var(--amber)" : "var(--text-0)";
  return (
    <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
      <div className="card-label">{label}</div>
      <div style={{ color, marginTop: "6px", fontWeight: 600 }}>{value}</div>
    </div>
  );
}

export default function AgentsClient() {
  const [selectedAgent, setSelectedAgent] = useState<AgentName>("overlord");
  const [agentFilter, setAgentFilter] = useState<AgentName | null>(null);
  const [statusFilter, setStatusFilter] = useState<AgentRunStatus | null>(null);
  const [runLimit, setRunLimit] = useState(RUN_PAGE_SIZE);
  const recentFailureSince = useMemo(
    () => new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    [],
  );

  const latestRunsQuery = useQuery({
    queryKey: getLatestAgentRunsQueryKey(),
    queryFn: fetchLatestAgentRuns,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const pauseStatesQuery = useQuery({
    queryKey: getAgentPauseStatesQueryKey(),
    queryFn: fetchAgentPauseStates,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
  const failureEventsQuery = useQuery({
    queryKey: getFailureEventsQueryKey({
      since: recentFailureSince,
      limit: 8,
    }),
    queryFn: () =>
      fetchFailureEvents({
        since: recentFailureSince,
        limit: 8,
      }),
    staleTime: 10_000,
    refetchInterval: 10_000,
  });

  const gatewayRuntimeQuery = useQuery({
    queryKey: ["gateway", "runtime"],
    queryFn: fetchGatewayRuntime,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const settingsSummaryQuery = useQuery({
    queryKey: ["settings", "summary"],
    queryFn: fetchSettingsSummary,
    staleTime: 60_000,
    refetchInterval: 60_000,
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

  const agents =
    latestRunsQuery.data?.agents ??
    AGENT_DISPLAY_ORDER.map((agentName) => ({
      agent_name: agentName,
      display_name: agentName[0].toUpperCase() + agentName.slice(1),
      role_label: "Loading…",
      description: "",
      implementation_status: "loading",
      runtime_kind: "loading",
      uses_github_token: false,
      uses_model: false,
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
    }));

  const selectedAgentData = agents.find((a) => a.agent_name === selectedAgent);
  const selectedPauseState = pauseStatesQuery.data?.find((p) => p.agent_name === selectedAgent);
  const selectedFailureEvent = failureEventsQuery.data?.find((event) => event.agent_name === selectedAgent);
  const isPaused = selectedPauseState?.is_paused || false;
  const runtimeAgent = gatewayRuntimeQuery.data?.runtime.agent_states.find(
    (agent) => agent.agent_key === selectedAgent,
  );
  const runtimeQueue = runtimeAgent && isLiveIntakeQueue(runtimeAgent.queue) ? runtimeAgent.queue : null;

  const cadence = deriveCadenceForAgent({
    agentId: selectedAgent,
    isPaused,
    pauseReason: selectedPauseState?.pause_reason,
    runtimeQueue,
    latestRun: selectedAgentData?.latest_run,
    settingsSummary: settingsSummaryQuery.data,
  });

  const activeCount =
    latestRunsQuery.data?.agents.filter((a) => {
      const paused = pauseStatesQuery.data?.find((p) => p.agent_name === a.agent_name)?.is_paused;
      return !paused && a.latest_run && a.latest_run.status === "completed";
    }).length || 0;

  const runningCount =
    latestRunsQuery.data?.agents.filter((a) => {
      const paused = pauseStatesQuery.data?.find((p) => p.agent_name === a.agent_name)?.is_paused;
      return !paused && a.latest_run && a.latest_run.status === "running";
    }).length || 0;

  const idleCount = Math.max(0, agents.length - activeCount - runningCount);

  const lastRunSuccessRate =
    selectedAgentData?.latest_run?.items_succeeded != null &&
    selectedAgentData?.latest_run?.items_processed != null &&
    selectedAgentData.latest_run.items_processed > 0
      ? Math.round(
          (selectedAgentData.latest_run.items_succeeded / selectedAgentData.latest_run.items_processed) * 100,
        )
      : null;

  const notes = [
    ...(selectedAgentData?.notes ?? []),
    ...(selectedAgentData?.latest_run?.error_summary ? [`Latest run: ${selectedAgentData.latest_run.error_summary}`] : []),
    ...((selectedAgentData?.runtime_progress?.details ?? []).slice(0, 2)),
    cadence.schedulerStatusExplanation,
  ];

  const firehoseInterval = findSettingEntry(settingsSummaryQuery.data, [
    "workers.FIREHOSE_INTERVAL_SECONDS",
    "FIREHOSE_INTERVAL_SECONDS",
  ]);
  const backfillInterval = findSettingEntry(settingsSummaryQuery.data, [
    "workers.BACKFILL_INTERVAL_SECONDS",
    "BACKFILL_INTERVAL_SECONDS",
  ]);
  const intakePacing = findSettingEntry(settingsSummaryQuery.data, [
    "workers.INTAKE_PACING_SECONDS",
    "INTAKE_PACING_SECONDS",
  ]);
  const githubBudget = findSettingEntry(settingsSummaryQuery.data, [
    "workers.GITHUB_REQUESTS_PER_MINUTE",
    "GITHUB_REQUESTS_PER_MINUTE",
  ]);
  const analystProvider = findSettingEntry(settingsSummaryQuery.data, [
    "workers.ANALYST_PROVIDER",
    "ANALYST_PROVIDER",
  ]);
  const anthropicKey = findSettingEntry(settingsSummaryQuery.data, [
    "workers.ANTHROPIC_API_KEY",
    "ANTHROPIC_API_KEY",
  ]);
  const analystModel = findSettingEntry(settingsSummaryQuery.data, [
    "workers.ANALYST_MODEL_NAME",
    "ANALYST_MODEL_NAME",
  ]);
  const geminiKey = findSettingEntry(settingsSummaryQuery.data, [
    "workers.GEMINI_API_KEY",
    "GEMINI_API_KEY",
  ]);
  const geminiBaseUrl = findSettingEntry(settingsSummaryQuery.data, [
    "workers.GEMINI_BASE_URL",
    "GEMINI_BASE_URL",
  ]);
  const geminiModel = findSettingEntry(settingsSummaryQuery.data, [
    "workers.GEMINI_MODEL_NAME",
    "GEMINI_MODEL_NAME",
  ]);

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Agents</span>
        <span className="topbar-breadcrumb">management</span>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "20px" }}>
        <div className="hero-strip mb-16">
          <div>
            <h2>Agent Management</h2>
            <div className="sub">Monitor, control, and inspect all named agents</div>
          </div>
          <div className="flex items-center gap-8">
            <span className="badge badge-green">{activeCount} Active</span>
            <span className="badge badge-yellow">{runningCount} Running</span>
            <span className="badge badge-muted">{idleCount} Idle</span>
          </div>
        </div>

        <OperationalAlertsPanel
          pauseStates={pauseStatesQuery.data ?? []}
          failureEvents={failureEventsQuery.data ?? []}
          agents={agents}
          agentStatuses={agents}
        />
        <GitHubBudgetPanel snapshot={gatewayRuntimeQuery.data?.runtime.github_api_budget} />

        <div style={{ display: "grid", gridTemplateColumns: "200px 1fr 280px", gap: "16px" }}>
          <div className="flex flex-col gap-8">
            <div className="section-head"><span className="section-title">Roster</span></div>
            {agents.map((agent) => {
              const pauseState = pauseStatesQuery.data?.find((p) => p.agent_name === agent.agent_name);
              const status = pauseState?.is_paused
                ? "red"
                : agent.latest_run?.status === "running"
                  ? "yellow"
                  : "green";

              return (
                <div
                  key={agent.agent_name}
                  className={`agent-card ${selectedAgent === agent.agent_name ? "selected" : ""}`}
                  data-testid={`agent-roster-card-${agent.agent_name}`}
                  onClick={() => setSelectedAgent(agent.agent_name)}
                >
                  <div className="flex items-center justify-between">
                    <span className="agent-name">{agent.display_name}</span>
                    <span className={`badge badge-${status}`}>●</span>
                  </div>
                  <div className="agent-role">{agent.role_label}</div>
                </div>
              );
            })}
          </div>

          <div>
            <div className="card mb-12" data-testid="agent-details-panel">
              <div className="card-header">
                <span className="card-title">{selectedAgentData?.display_name ?? selectedAgent}</span>
                <span className={`badge ${isPaused ? "badge-red" : cadence.mode === "interval" && (cadence.remainingSeconds ?? 0) > 0 ? "badge-yellow" : "badge-green"}`}>
                  {isPaused ? "Paused" : cadence.stateLabel}
                </span>
              </div>
              <div style={{ fontSize: "12px", color: "var(--text-2)", marginBottom: "12px" }}>
                {selectedAgentData?.role_label ?? "Loading role…"}
              </div>
              <div className="grid g4 mb-12">
                <div>
                  <div className="card-label">Last Run</div>
                  <div style={{ fontSize: "16px", fontWeight: 600, color: "var(--text-0)", marginTop: "4px" }}>
                    {selectedAgentData?.latest_run?.started_at
                      ? `${formatRelative(selectedAgentData.latest_run.started_at)}`
                      : "—"}
                  </div>
                </div>
                <div>
                  <div className="card-label">Items</div>
                  <div style={{ fontSize: "16px", fontWeight: 600, color: "var(--text-0)", marginTop: "4px", fontFamily: "var(--mono)" }}>
                    {selectedAgentData?.latest_run?.items_processed?.toLocaleString() ?? "0"}
                  </div>
                </div>
                <div>
                  <div className="card-label">Live Work</div>
                  <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-0)", marginTop: "4px", lineHeight: "1.5" }}>
                    {selectedAgentData?.runtime_progress?.current_activity ?? "No live runtime snapshot"}
                  </div>
                </div>
                <div>
                  <div className="card-label">Provider</div>
                  <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--green)", marginTop: "4px", fontFamily: "var(--mono)" }}>
                    {selectedAgentData?.latest_run?.provider_name ?? selectedAgentData?.configured_provider ?? "local-only"}
                  </div>
                </div>
              </div>
              <div style={{ fontSize: "12px", color: "var(--text-2)", marginBottom: "12px", lineHeight: "1.6" }}>
                <div><span className="card-label">Runtime</span></div>
                <div style={{ marginTop: "4px" }}>{selectedAgentData?.description ?? "Loading runtime details…"}</div>
                <div style={{ marginTop: "8px", fontFamily: "var(--mono)", fontSize: "11px", color: "var(--text-3)" }}>
                  Kind: {selectedAgentData?.runtime_kind ?? "loading"} · Status: {selectedAgentData?.implementation_status ?? "loading"}
                </div>
                <div style={{ marginTop: "6px", fontFamily: "var(--mono)", fontSize: "11px", color: "var(--text-3)" }}>
                  GitHub token: {selectedAgentData?.uses_github_token ? "yes" : "no"} · Model-backed: {selectedAgentData?.uses_model ? "yes" : "no"}
                </div>
              </div>
              <div className="flex gap-8">
                {isPaused ? <ResumeAgentButton agentName={selectedAgent} /> : <PauseAgentButton agentName={selectedAgent} />}
              </div>
            </div>

            <div className="mb-12">
              <AgentOperatorSummary
                entry={selectedAgentData}
                pauseState={selectedPauseState}
                failureEvent={selectedFailureEvent}
              />
            </div>

            <div className="section-head"><span className="section-title">Runtime Notes</span><div className="section-line"></div></div>
            <div className="card mb-12">
              <div style={{ fontSize: "13px", color: "var(--text-1)", lineHeight: "1.75" }}>
                {notes.length ? (
                  notes.map((note, index) => (
                    <div key={`${note}-${index}`} style={{ padding: "10px 0", borderBottom: index < notes.length - 1 ? "1px solid var(--border)" : "none" }}>
                      {note}
                    </div>
                  ))
                ) : (
                  <div style={{ color: "var(--text-3)", textAlign: "center", padding: "20px" }}>
                    No live runtime notes recorded for this agent.
                  </div>
                )}
              </div>
            </div>

            <div className="section-head"><span className="section-title">Last Run Metrics</span><div className="section-line"></div></div>
            <div className="card mb-12">
              <div className="grid g3">
                <div>
                  <div className="card-label">Processed</div>
                  <div style={{ fontSize: "20px", fontWeight: 700, color: "var(--text-0)", fontFamily: "var(--mono)" }}>
                    {selectedAgentData?.latest_run?.items_processed?.toLocaleString() ?? "0"}
                  </div>
                </div>
                <div>
                  <div className="card-label">Succeeded</div>
                  <div style={{ fontSize: "20px", fontWeight: 700, color: "var(--green)", fontFamily: "var(--mono)" }}>
                    {selectedAgentData?.latest_run?.items_succeeded?.toLocaleString() ?? "0"}
                  </div>
                </div>
                <div>
                  <div className="card-label">Failed</div>
                  <div style={{ fontSize: "20px", fontWeight: 700, color: selectedAgentData?.latest_run?.items_failed ? "var(--amber)" : "var(--text-0)", fontFamily: "var(--mono)" }}>
                    {selectedAgentData?.latest_run?.items_failed?.toLocaleString() ?? "0"}
                  </div>
                </div>
              </div>
              <div style={{ marginTop: "12px", display: "grid", gap: "8px", gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
                <StatusCard label="Duration" value={formatDuration(selectedAgentData?.latest_run?.duration_seconds)} />
                <StatusCard
                  label="Success Rate"
                  value={lastRunSuccessRate != null ? `${lastRunSuccessRate}%` : "Unavailable"}
                  tone={lastRunSuccessRate != null && lastRunSuccessRate < 100 ? "warn" : "good"}
                />
              </div>
            </div>

            <div className="section-head"><span className="section-title">Token Usage & Budget</span><div className="section-line"></div></div>
            <div className="card mb-12">
              <div style={{ fontSize: "12px", color: "var(--text-2)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <span>Last 24h</span>
                  <span style={{ fontFamily: "var(--mono)", color: "var(--text-0)" }}>{formatTokenCount(selectedAgentData?.token_usage_24h || 0)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <span>Input</span>
                  <span style={{ fontFamily: "var(--mono)", color: "var(--green)" }}>{formatTokenCount(selectedAgentData?.input_tokens_24h || 0)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0" }}>
                  <span>Output</span>
                  <span style={{ fontFamily: "var(--mono)", color: "var(--text-0)" }}>{formatTokenCount(selectedAgentData?.output_tokens_24h || 0)}</span>
                </div>
              </div>
              <div style={{ marginTop: "10px", fontSize: "11px", color: "var(--text-3)", fontFamily: "var(--mono)" }}>
                {selectedAgentData?.uses_model
                  ? `Latest provider: ${selectedAgentData?.latest_run?.provider_name ?? selectedAgentData?.configured_provider ?? "unknown"}`
                  : "No model-backed usage is expected for this agent in the current runtime."}
              </div>
            </div>

            <div className="section-head"><span className="section-title">Run History</span><div className="section-line"></div></div>
            {runsQuery.isError ? (
              <div className="card" style={{ background: "var(--red-dim)", borderColor: "var(--red)" }}>
                Unable to load run history
              </div>
            ) : (
              <AgentRunHistoryTable
                agentFilter={agentFilter}
                canLoadMore={!runsQuery.isLoading && runLimit < MAX_RUN_PAGE_SIZE && (runsQuery.data?.length ?? 0) >= runLimit}
                isLoading={runsQuery.isLoading}
                isLoadingMore={runsQuery.isFetching && !runsQuery.isLoading}
                onAgentFilterChange={setAgentFilter}
                onLoadMore={() => setRunLimit((limit) => Math.min(limit + RUN_PAGE_SIZE, MAX_RUN_PAGE_SIZE))}
                onStatusFilterChange={setStatusFilter}
                runs={runsQuery.data ?? []}
                statusFilter={statusFilter}
              />
            )}
          </div>

          <div>
            <div className="section-head"><span className="section-title">Controls</span></div>
            <div className="card mb-12">
              <div className="flex gap-8" style={{ flexDirection: "column" }}>
                {isPaused ? <ResumeAgentButton agentName={selectedAgent} /> : <PauseAgentButton agentName={selectedAgent} />}
                <div style={{ fontSize: "12px", color: "var(--text-2)", lineHeight: "1.6" }}>
                  {selectedAgent === "analyst"
                    ? "Use the Control Panel to change Analyst provider mode, model routing, and shared intake pacing. This page mirrors the current live runtime state and pause controls."
                    : "Use the Control Panel for editable cadence and timeline changes. This page mirrors live runtime state and pause controls."}
                </div>
              </div>
            </div>

            <div className="section-head"><span className="section-title">Schedule</span></div>
            <div className="card mb-12">
              <div style={{ fontSize: "12px", color: "var(--text-2)" }}>
                <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <strong style={{ color: "var(--text-0)" }}>Execution mode:</strong> {titleCase(cadence.mode)}
                </div>
                <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <strong style={{ color: "var(--text-0)" }}>State:</strong> {cadence.stateLabel}
                </div>
                <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <strong style={{ color: "var(--text-0)" }}>Scheduled run:</strong>{" "}
                  {cadence.nextDueAt ? `${formatTimeUntilScheduledRun(cadence.nextDueAt)} (${formatTimestamp(cadence.nextDueAt)})` : cadence.mode === "interval" ? "Not scheduled yet" : "Triggered by work, not by time"}
                </div>
                <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <strong style={{ color: "var(--text-0)" }}>Interval:</strong>{" "}
                  {cadence.intervalSeconds != null ? formatDuration(cadence.intervalSeconds) : "Not recurring"}
                </div>
                <div style={{ padding: "8px 0" }}>
                  <strong style={{ color: "var(--text-0)" }}>Progress last saved at:</strong>{" "}
                  {cadence.lastCheckpointAt ? `${formatRelative(cadence.lastCheckpointAt)} (${formatTimestamp(cadence.lastCheckpointAt)})` : "Never"}
                </div>
              </div>
            </div>

            <div className="section-head"><span className="section-title">Live Runtime</span></div>
            <div className="card mb-12">
              <div style={{ fontSize: "12px", color: "var(--text-2)", lineHeight: "1.6" }}>
                <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <strong style={{ color: "var(--text-0)" }}>Current activity:</strong>{" "}
                  {selectedAgentData?.runtime_progress?.current_activity ?? "No live runtime snapshot"}
                </div>
                <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <strong style={{ color: "var(--text-0)" }}>Current target:</strong>{" "}
                  {selectedAgentData?.runtime_progress?.current_target ?? "Unavailable"}
                </div>
                <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <strong style={{ color: "var(--text-0)" }}>Progress:</strong>{" "}
                  {selectedAgentData?.runtime_progress?.completed_count != null &&
                  selectedAgentData?.runtime_progress?.total_count != null
                    ? `${selectedAgentData.runtime_progress.completed_count} / ${selectedAgentData.runtime_progress.total_count} ${selectedAgentData.runtime_progress.unit_label ?? "items"}`
                    : selectedAgentData?.runtime_progress?.remaining_count != null
                      ? `${selectedAgentData.runtime_progress.remaining_count} ${selectedAgentData.runtime_progress.unit_label ?? "items"} remaining`
                      : "Unavailable"}
                  {selectedAgentData?.runtime_progress?.progress_percent != null
                    ? ` (${selectedAgentData.runtime_progress.progress_percent}%)`
                    : ""}
                </div>
                <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <strong style={{ color: cadence.schedulerStatusTone === "good" ? "var(--green)" : cadence.schedulerStatusTone === "warn" ? "var(--amber)" : "var(--text-0)" }}>
                    {cadence.schedulerStatusLabel}
                  </strong>
                </div>
                <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  {cadence.schedulerStatusExplanation}
                </div>
                <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <strong style={{ color: "var(--text-0)" }}>Snapshot source:</strong>{" "}
                  {selectedAgentData?.runtime_progress?.source ?? "Unavailable"}
                </div>
                <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <strong style={{ color: "var(--text-0)" }}>Runtime updated at:</strong>{" "}
                  {selectedAgentData?.runtime_progress?.updated_at
                    ? `${formatRelative(selectedAgentData.runtime_progress.updated_at)} (${formatTimestamp(selectedAgentData.runtime_progress.updated_at)})`
                    : "Unavailable"}
                </div>
                <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <strong style={{ color: "var(--text-0)" }}>Last scheduler evidence:</strong>{" "}
                  {cadence.lastSchedulerEvidenceAt ? `${formatRelative(cadence.lastSchedulerEvidenceAt)} (${formatTimestamp(cadence.lastSchedulerEvidenceAt)})` : "Unavailable"}
                </div>
                {selectedAgent === "firehose" ? (
                  <>
                    <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                      <strong style={{ color: "var(--text-0)" }}>New feed anchor:</strong>{" "}
                      {runtimeQueue?.checkpoint.kind === "firehose" ? runtimeQueue.checkpoint.new_anchor_date ?? "Unavailable" : "Unavailable"}
                    </div>
                    <div style={{ padding: "8px 0" }}>
                      <strong style={{ color: "var(--text-0)" }}>Trending feed anchor:</strong>{" "}
                      {runtimeQueue?.checkpoint.kind === "firehose" ? runtimeQueue.checkpoint.trending_anchor_date ?? "Unavailable" : "Unavailable"}
                    </div>
                  </>
                ) : null}
                {selectedAgent === "backfill" ? (
                  <>
                    <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                      <strong style={{ color: "var(--text-0)" }}>Oldest date in current window:</strong>{" "}
                      {runtimeQueue?.checkpoint.kind === "backfill" ? runtimeQueue.checkpoint.window_start_date ?? "Unavailable" : "Unavailable"}
                    </div>
                    <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                      <strong style={{ color: "var(--text-0)" }}>Newest boundary:</strong>{" "}
                      {runtimeQueue?.checkpoint.kind === "backfill" ? runtimeQueue.checkpoint.created_before_boundary ?? "Unavailable" : "Unavailable"}
                    </div>
                    <div style={{ padding: "8px 0" }}>
                      <strong style={{ color: "var(--text-0)" }}>Current cursor:</strong>{" "}
                      {runtimeQueue?.checkpoint.kind === "backfill" ? runtimeQueue.checkpoint.created_before_cursor ?? "Not currently narrowed" : "Unavailable"}
                    </div>
                  </>
                ) : null}
                {selectedAgent !== "firehose" && selectedAgent !== "backfill" ? (
                  <>
                    <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                      <strong style={{ color: "var(--text-0)" }}>Provider:</strong>{" "}
                      {selectedAgent === "analyst"
                        ? analystProvider?.value ?? selectedAgentData?.configured_provider ?? "none"
                        : selectedAgentData?.configured_provider ?? "none"}
                    </div>
                    <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                      <strong style={{ color: "var(--text-0)" }}>Model:</strong>{" "}
                      {selectedAgent === "analyst"
                        ? analystModel?.value ?? selectedAgentData?.configured_model ?? "none"
                        : selectedAgentData?.configured_model ?? "none"}
                    </div>
                    <div style={{ padding: "8px 0", borderBottom: selectedAgent === "analyst" ? "1px solid var(--border)" : "none" }}>
                      <strong style={{ color: "var(--text-0)" }}>Uses GitHub token:</strong>{" "}
                      {selectedAgentData?.uses_github_token ? "yes" : "no"}
                    </div>
                    {selectedAgent === "analyst" ? (
                      <>
                        <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                          <strong style={{ color: "var(--text-0)" }}>Anthropic key:</strong>{" "}
                          {anthropicKey?.value ?? "Unavailable"}
                        </div>
                        <div style={{ padding: "8px 0" }}>
                          <strong style={{ color: "var(--text-0)" }}>Gemini key:</strong>{" "}
                          {geminiKey?.value ?? "Unavailable"}
                        </div>
                      </>
                    ) : null}
                  </>
                ) : null}
              </div>
            </div>

            <div className="section-head"><span className="section-title">Runtime Settings</span></div>
            <div className="card">
              <div style={{ fontSize: "12px", color: "var(--text-2)", lineHeight: "1.6" }}>
                {selectedAgent === "firehose" ? (
                  <>
                    <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                      Interval: {firehoseInterval?.value ? formatDuration(Number(firehoseInterval.value)) : "Unavailable"}
                    </div>
                    <div style={{ padding: "8px 0" }}>
                      Shared intake pacing: {intakePacing?.value ? formatDuration(Number(intakePacing.value)) : "Unavailable"}
                    </div>
                  </>
                ) : null}
                {selectedAgent === "backfill" ? (
                  <>
                    <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                      Interval: {backfillInterval?.value ? formatDuration(Number(backfillInterval.value)) : "Unavailable"}
                    </div>
                    <div style={{ padding: "8px 0" }}>
                      Shared intake pacing: {intakePacing?.value ? formatDuration(Number(intakePacing.value)) : "Unavailable"}
                    </div>
                  </>
                ) : null}
                {selectedAgent !== "firehose" && selectedAgent !== "backfill" ? (
                  <>
                    {selectedAgent === "analyst" ? (
                      <>
                        <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                          Provider mode: {analystProvider?.value ?? "Unavailable"}
                        </div>
                        <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                          Anthropic model: {analystModel?.value ?? "Unavailable"}
                        </div>
                        <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                          Gemini base URL: {geminiBaseUrl?.value ?? "Unavailable"}
                        </div>
                        <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                          Gemini model: {geminiModel?.value ?? "Unavailable"}
                        </div>
                        <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                          GitHub request budget: {githubBudget?.value ? `${githubBudget.value} req/min` : "Unavailable"}
                        </div>
                        <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                          Shared intake pacing: {intakePacing?.value ? formatDuration(Number(intakePacing.value)) : "Unavailable"}
                        </div>
                        <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                          Anthropic key: {anthropicKey?.value ?? "Unavailable"}
                        </div>
                        <div style={{ padding: "8px 0" }}>
                          Gemini key: {geminiKey?.value ?? "Unavailable"}
                        </div>
                      </>
                    ) : (
                      <div>
                        Use the Control Panel for editable runtime settings. This page mirrors the current live values and scheduling state.
                      </div>
                    )}
                  </>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

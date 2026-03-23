import type {
  AgentName,
  AgentPauseState,
  AgentRuntimeProgress,
  AgentStatusEntry,
  FailureEventPayload,
} from "@/api/agents";

function toTimestamp(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function latestKnownRecoveryTimestamp(
  statusEntry: AgentStatusEntry | undefined,
  pauseState: AgentPauseState | undefined,
): number | null {
  const candidates = [
    pauseState?.resumed_at ?? null,
    statusEntry?.latest_run?.completed_at ?? null,
    statusEntry?.latest_run?.started_at ?? null,
    statusEntry?.runtime_progress?.updated_at ?? null,
  ]
    .map((value) => toTimestamp(value))
    .filter((value): value is number => value != null);

  if (candidates.length === 0) {
    return null;
  }
  return Math.max(...candidates);
}

function hasFreshRuntimeUpdate(progress: AgentRuntimeProgress | null | undefined): boolean {
  if (!progress?.updated_at) {
    return false;
  }
  const updatedAt = toTimestamp(progress.updated_at);
  if (updatedAt == null) {
    return false;
  }
  return Date.now() - updatedAt <= 2 * 60 * 1000;
}

function isRuntimeActivityWaiting(progress: AgentRuntimeProgress | null | undefined): boolean {
  const activity = progress?.current_activity?.trim().toLowerCase() ?? "";
  const statusLabel = progress?.status_label?.trim().toLowerCase() ?? "";
  return (
    activity.startsWith("waiting ") ||
    activity.startsWith("idle") ||
    activity.includes("no active") ||
    activity.includes("no accepted repositories") ||
    statusLabel === "idle" ||
    statusLabel === "waiting"
  );
}

export function isAgentEffectivelyRunning(
  statusEntry: AgentStatusEntry | undefined,
  pauseState: AgentPauseState | undefined,
): boolean {
  if (!statusEntry || pauseState?.is_paused) {
    return false;
  }
  if (statusEntry.latest_run?.status === "running") {
    return true;
  }
  return hasFreshRuntimeUpdate(statusEntry.runtime_progress) && !isRuntimeActivityWaiting(statusEntry.runtime_progress);
}

export function isFailureStillActive(
  event: FailureEventPayload,
  statusEntry: AgentStatusEntry | undefined,
  pauseState: AgentPauseState | undefined,
): boolean {
  if (pauseState?.is_paused) {
    return pauseState.triggered_by_event_id === event.id;
  }

  const failureAt = toTimestamp(event.created_at);
  const recoveryAt = latestKnownRecoveryTimestamp(statusEntry, pauseState);
  if (failureAt == null || recoveryAt == null) {
    return true;
  }

  if (recoveryAt <= failureAt) {
    return true;
  }

  const latestRunStatus = statusEntry?.latest_run?.status;
  if (latestRunStatus === "running" || latestRunStatus === "completed") {
    return false;
  }

  if (pauseState?.resumed_at && recoveryAt === toTimestamp(pauseState.resumed_at)) {
    return false;
  }

  return event.failure_classification !== "rate_limited";
}

export function buildLatestActiveFailureByAgent(
  failureEvents: FailureEventPayload[],
  statusEntries: AgentStatusEntry[],
  pauseStates: AgentPauseState[],
): Map<AgentName, FailureEventPayload> {
  const pauseMap = new Map<AgentName, AgentPauseState>(
    pauseStates.map((state) => [state.agent_name, state]),
  );
  const statusMap = new Map<AgentName, AgentStatusEntry>(
    statusEntries.map((entry) => [entry.agent_name, entry]),
  );
  const result = new Map<AgentName, FailureEventPayload>();

  for (const event of failureEvents) {
    if (result.has(event.agent_name)) {
      continue;
    }
    if (isFailureStillActive(event, statusMap.get(event.agent_name), pauseMap.get(event.agent_name))) {
      result.set(event.agent_name, event);
    }
  }

  return result;
}

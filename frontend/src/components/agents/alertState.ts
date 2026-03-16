import type {
  AgentName,
  AgentPauseState,
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

export function isFailureStillActive(
  event: FailureEventPayload,
  statusEntry: AgentStatusEntry | undefined,
  pauseState: AgentPauseState | undefined,
): boolean {
  if (pauseState?.is_paused) {
    return true;
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

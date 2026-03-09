interface RuntimeRefreshStatus {
  refreshInFlight: boolean;
  consecutiveFailures: number;
  pollingPaused: boolean;
}

function formatTimestamp(value: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  }).format(new Date(value));
}

export function formatLastUpdatedLabel(
  lastUpdatedAt: string | null,
  timeZone: string,
): string {
  if (!lastUpdatedAt) {
    return "Waiting for first successful sync";
  }

  return formatTimestamp(lastUpdatedAt, timeZone);
}

export function getPollingStatusLabel(
  snapshot: RuntimeRefreshStatus,
  hasSuccessfulSnapshot: boolean,
): string {
  if (snapshot.refreshInFlight) {
    return "Refreshing now";
  }
  if (!hasSuccessfulSnapshot) {
    return "Waiting for first successful sync";
  }
  if (snapshot.pollingPaused) {
    return "Polling paused";
  }
  return "Backend polling active";
}

export function getPollingStatusAnnouncement(
  snapshot: RuntimeRefreshStatus,
  hasSuccessfulSnapshot: boolean,
): string {
  const statusLabel = getPollingStatusLabel(snapshot, hasSuccessfulSnapshot);
  if (snapshot.consecutiveFailures === 0) {
    return statusLabel;
  }
  return `${statusLabel}. Consecutive failures: ${snapshot.consecutiveFailures}.`;
}

export function getPollingIndicatorClassName(
  snapshot: RuntimeRefreshStatus,
  hasSuccessfulSnapshot: boolean,
): string {
  if (snapshot.refreshInFlight) {
    return "animate-pulse bg-orange-600";
  }
  if (!hasSuccessfulSnapshot || snapshot.pollingPaused) {
    return "bg-amber-500";
  }
  return "bg-emerald-500";
}

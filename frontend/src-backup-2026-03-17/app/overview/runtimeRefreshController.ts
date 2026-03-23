export const RUNTIME_REFRESH_INTERVAL_MS = 15_000;
export const MAX_CONSECUTIVE_REFRESH_FAILURES = 3;
export const MAX_REFRESH_BACKOFF_INTERVAL_MS = 120_000;

export interface RuntimeRefreshSnapshot {
  refreshInFlight: boolean;
  consecutiveFailures: number;
  pollingPaused: boolean;
}

interface RuntimeRefreshScheduler {
  setInterval(callback: () => void, delayMs: number): number;
  clearInterval(intervalId: number): void;
}

interface RuntimeRefreshVisibilitySource {
  getVisibilityState(): DocumentVisibilityState;
  addEventListener(
    eventName: "visibilitychange",
    listener: () => void,
  ): void;
  removeEventListener(
    eventName: "visibilitychange",
    listener: () => void,
  ): void;
}

interface RuntimeRefreshControllerOptions {
  onRefreshRequest: () => Promise<boolean>;
  onStateChange?: (snapshot: RuntimeRefreshSnapshot) => void;
  scheduler: RuntimeRefreshScheduler;
  visibilitySource: RuntimeRefreshVisibilitySource;
  now?: () => number;
  intervalMs?: number;
  maxConsecutiveFailures?: number;
}

export interface RuntimeRefreshController {
  start(): void;
  stop(): void;
  triggerManualRefresh(): Promise<void>;
  getSnapshot(): RuntimeRefreshSnapshot;
}

function createSnapshot(
  refreshInFlight: boolean,
  consecutiveFailures: number,
  pollingPaused: boolean,
): RuntimeRefreshSnapshot {
  return {
    refreshInFlight,
    consecutiveFailures,
    pollingPaused,
  };
}

export function createRuntimeRefreshController(
  options: RuntimeRefreshControllerOptions,
): RuntimeRefreshController {
  const intervalMs = options.intervalMs ?? RUNTIME_REFRESH_INTERVAL_MS;
  const maxConsecutiveFailures =
    options.maxConsecutiveFailures ?? MAX_CONSECUTIVE_REFRESH_FAILURES;
  const now = options.now ?? Date.now;

  let disposed = false;
  let started = false;
  let refreshInFlight = false;
  let consecutiveFailures = 0;
  let pollingPaused = false;
  let nextAllowedRefreshAt = 0;
  let intervalId: number | null = null;

  const emitStateChange = () => {
    options.onStateChange?.(
      createSnapshot(refreshInFlight, consecutiveFailures, pollingPaused),
    );
  };

  const runRefresh = async (trigger: "interval" | "visibility" | "manual") => {
    if (disposed || refreshInFlight) {
      return;
    }

    if (pollingPaused && trigger !== "manual") {
      return;
    }

    if (trigger !== "manual" && nextAllowedRefreshAt > now()) {
      return;
    }

    refreshInFlight = true;
    emitStateChange();

    try {
      const didSucceed = await options.onRefreshRequest();
      if (disposed) {
        return;
      }

      if (didSucceed) {
        consecutiveFailures = 0;
        pollingPaused = false;
        nextAllowedRefreshAt = 0;
      } else {
        consecutiveFailures += 1;
        pollingPaused = consecutiveFailures >= maxConsecutiveFailures;
        const backoffMultiplier = 2 ** Math.max(consecutiveFailures - 1, 0);
        nextAllowedRefreshAt =
          now() +
          Math.min(
            intervalMs * backoffMultiplier,
            MAX_REFRESH_BACKOFF_INTERVAL_MS,
          );
      }
    } finally {
      refreshInFlight = false;
      if (!disposed) {
        emitStateChange();
      }
    }
  };

  const handleInterval = () => {
    void runRefresh("interval");
  };

  const handleVisibilityChange = () => {
    if (options.visibilitySource.getVisibilityState() === "visible") {
      void runRefresh("visibility");
    }
  };

  return {
    start() {
      if (started || disposed) {
        return;
      }

      started = true;
      intervalId = options.scheduler.setInterval(handleInterval, intervalMs);
      options.visibilitySource.addEventListener(
        "visibilitychange",
        handleVisibilityChange,
      );
      emitStateChange();
    },
    stop() {
      if (disposed) {
        return;
      }

      disposed = true;
      if (intervalId !== null) {
        options.scheduler.clearInterval(intervalId);
      }
      options.visibilitySource.removeEventListener(
        "visibilitychange",
        handleVisibilityChange,
      );
    },
    async triggerManualRefresh() {
      await runRefresh("manual");
    },
    getSnapshot() {
      return createSnapshot(refreshInFlight, consecutiveFailures, pollingPaused);
    },
  };
}

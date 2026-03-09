import assert from "node:assert/strict";
import test from "node:test";

import {
  createRuntimeRefreshController,
  MAX_CONSECUTIVE_REFRESH_FAILURES,
  MAX_REFRESH_BACKOFF_INTERVAL_MS,
  RUNTIME_REFRESH_INTERVAL_MS,
  type RuntimeRefreshSnapshot,
} from "../../src/app/overview/runtimeRefreshController.ts";

class FakeScheduler {
  callback: (() => void) | null = null;
  clearedIntervalId: number | null = null;
  delayMs: number | null = null;

  setInterval(callback: () => void, delayMs: number): number {
    this.callback = callback;
    this.delayMs = delayMs;
    return 1;
  }

  clearInterval(intervalId: number): void {
    this.clearedIntervalId = intervalId;
    this.callback = null;
  }

  async tick(): Promise<void> {
    assert.ok(this.callback, "Expected interval callback to be registered.");
    await this.callback();
  }
}

class FakeVisibilitySource {
  listener: (() => void) | null = null;
  state: DocumentVisibilityState = "hidden";

  getVisibilityState(): DocumentVisibilityState {
    return this.state;
  }

  addEventListener(
    eventName: "visibilitychange",
    listener: () => void,
  ): void {
    assert.equal(eventName, "visibilitychange");
    this.listener = listener;
  }

  removeEventListener(
    eventName: "visibilitychange",
    listener: () => void,
  ): void {
    assert.equal(eventName, "visibilitychange");
    if (this.listener === listener) {
      this.listener = null;
    }
  }

  async emit(state: DocumentVisibilityState): Promise<void> {
    this.state = state;
    await this.listener?.();
  }
}

test("runtime refresh controller schedules polling with the expected interval", () => {
  const scheduler = new FakeScheduler();
  const visibilitySource = new FakeVisibilitySource();
  const controller = createRuntimeRefreshController({
    onRefreshRequest: async () => true,
    scheduler,
    visibilitySource,
  });

  controller.start();

  assert.equal(scheduler.delayMs, RUNTIME_REFRESH_INTERVAL_MS);
  assert.deepEqual(controller.getSnapshot(), {
    refreshInFlight: false,
    consecutiveFailures: 0,
    pollingPaused: false,
  });
});

test("runtime refresh controller triggers a refresh when the page becomes visible", async () => {
  const scheduler = new FakeScheduler();
  const visibilitySource = new FakeVisibilitySource();
  const triggers: string[] = [];

  const controller = createRuntimeRefreshController({
    onRefreshRequest: async () => {
      triggers.push("refresh");
      return true;
    },
    scheduler,
    visibilitySource,
  });

  controller.start();
  await visibilitySource.emit("hidden");
  assert.equal(triggers.length, 0);

  await visibilitySource.emit("visible");
  assert.equal(triggers.length, 1);
});

test("runtime refresh controller pauses interval refreshes after repeated failures", async () => {
  const scheduler = new FakeScheduler();
  const visibilitySource = new FakeVisibilitySource();
  let currentTimeMs = 0;
  const refreshResults = [
    false,
    false,
    false,
    true,
    true,
  ];
  const snapshots: RuntimeRefreshSnapshot[] = [];

  const controller = createRuntimeRefreshController({
    onRefreshRequest: async () => {
      const result = refreshResults.shift();
      assert.notEqual(result, undefined);
      return result;
    },
    onStateChange(snapshot) {
      snapshots.push(snapshot);
    },
    now: () => currentTimeMs,
    scheduler,
    visibilitySource,
  });

  controller.start();
  await scheduler.tick();
  currentTimeMs += RUNTIME_REFRESH_INTERVAL_MS;
  await scheduler.tick();
  currentTimeMs += RUNTIME_REFRESH_INTERVAL_MS;
  await scheduler.tick();
  currentTimeMs += RUNTIME_REFRESH_INTERVAL_MS;
  await scheduler.tick();

  assert.deepEqual(controller.getSnapshot(), {
    refreshInFlight: false,
    consecutiveFailures: MAX_CONSECUTIVE_REFRESH_FAILURES,
    pollingPaused: true,
  });

  currentTimeMs += RUNTIME_REFRESH_INTERVAL_MS;
  await scheduler.tick();
  assert.equal(refreshResults.length, 2, "Polling should not continue while paused.");

  await controller.triggerManualRefresh();
  assert.deepEqual(controller.getSnapshot(), {
    refreshInFlight: false,
    consecutiveFailures: 0,
    pollingPaused: false,
  });

  await scheduler.tick();
  assert.equal(refreshResults.length, 0);
  assert.ok(
    snapshots.some(
      (snapshot) =>
        snapshot.pollingPaused &&
        snapshot.consecutiveFailures === MAX_CONSECUTIVE_REFRESH_FAILURES,
    ),
  );
});

test("runtime refresh controller applies exponential backoff before the pause threshold", async () => {
  const scheduler = new FakeScheduler();
  const visibilitySource = new FakeVisibilitySource();
  let currentTimeMs = 0;
  let refreshCount = 0;

  const controller = createRuntimeRefreshController({
    intervalMs: 1000,
    maxConsecutiveFailures: 10,
    now: () => currentTimeMs,
    onRefreshRequest: async () => {
      refreshCount += 1;
      return false;
    },
    scheduler,
    visibilitySource,
  });

  controller.start();
  await scheduler.tick();
  assert.equal(refreshCount, 1);

  currentTimeMs += 1000;
  await scheduler.tick();
  assert.equal(refreshCount, 2);

  currentTimeMs += 1000;
  await scheduler.tick();
  assert.equal(refreshCount, 2);

  currentTimeMs += 1000;
  await scheduler.tick();
  assert.equal(refreshCount, 3);

  currentTimeMs += 1000;
  await scheduler.tick();
  assert.equal(refreshCount, 3);

  currentTimeMs += 3000;
  await scheduler.tick();
  assert.equal(refreshCount, 4);

  currentTimeMs += MAX_REFRESH_BACKOFF_INTERVAL_MS;
  await scheduler.tick();
  assert.equal(refreshCount, 5);
});

test("runtime refresh controller unregisters listeners when stopped", async () => {
  const scheduler = new FakeScheduler();
  const visibilitySource = new FakeVisibilitySource();
  let refreshCount = 0;

  const controller = createRuntimeRefreshController({
    onRefreshRequest: async () => {
      refreshCount += 1;
      return true;
    },
    scheduler,
    visibilitySource,
  });

  controller.start();
  controller.stop();

  assert.equal(scheduler.clearedIntervalId, 1);
  assert.equal(visibilitySource.listener, null);

  await visibilitySource.emit("visible");
  assert.equal(refreshCount, 0);
});

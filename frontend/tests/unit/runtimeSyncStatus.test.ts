import assert from "node:assert/strict";
import test from "node:test";

import {
  formatLastUpdatedLabel,
  getPollingIndicatorClassName,
  getPollingStatusAnnouncement,
  getPollingStatusLabel,
} from "../../src/app/overview/runtimeSyncStatus.ts";

test("formatLastUpdatedLabel reports missing successful snapshot", () => {
  assert.equal(
    formatLastUpdatedLabel(null, "UTC"),
    "Waiting for first successful sync",
  );
});

test("polling status stays non-healthy before the first successful snapshot", () => {
  const snapshot = {
    refreshInFlight: false,
    consecutiveFailures: 0,
    pollingPaused: false,
  };

  assert.equal(
    getPollingStatusLabel(snapshot, false),
    "Waiting for first successful sync",
  );
  assert.equal(
    getPollingStatusAnnouncement(snapshot, false),
    "Waiting for first successful sync",
  );
  assert.equal(
    getPollingIndicatorClassName(snapshot, false),
    "bg-amber-500",
  );
});

test("polling status returns to healthy after a successful snapshot", () => {
  const snapshot = {
    refreshInFlight: false,
    consecutiveFailures: 0,
    pollingPaused: false,
  };

  assert.equal(getPollingStatusLabel(snapshot, true), "Backend polling active");
  assert.equal(getPollingIndicatorClassName(snapshot, true), "bg-emerald-500");
});

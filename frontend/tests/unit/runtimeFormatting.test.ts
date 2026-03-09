import assert from "node:assert/strict";
import test from "node:test";

import { renderCheckpointRows } from "../../src/app/overview/runtimeFormatting.ts";

test("backfill checkpoint rows format created_before_cursor as a timestamp", () => {
  const rows = renderCheckpointRows(
    {
      status: "live",
      source_of_truth: "agentic-workflow",
      pending_items: 2,
      total_items: 5,
      state_counts: {
        pending: 2,
        in_progress: 1,
        completed: 2,
        failed: 0,
      },
      checkpoint: {
        kind: "backfill",
        next_page: 3,
        last_checkpointed_at: "2026-03-07T09:45:00Z",
        mirror_snapshot_generated_at: "2026-03-07T09:46:00Z",
        window_start_date: "2025-01-01",
        created_before_boundary: "2025-01-31",
        created_before_cursor: "2025-01-15T12:00:00Z",
        exhausted: false,
      },
      notes: [],
    },
    "UTC",
  );

  const createdBeforeCursor = rows.find(([label]) => label === "Created before cursor");
  assert.deepEqual(createdBeforeCursor, [
    "Created before cursor",
    "Jan 15, 2025, 12:00 PM",
  ]);
});

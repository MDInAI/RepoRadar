import type { GatewayAgentIntakeQueueSummary } from "../../lib/gateway-contract";
import { formatAppDateTime } from "../../lib/time";

export function formatOptionalValue(value: string | number | boolean | null): string {
  if (value === null) {
    return "Not checkpointed yet";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return String(value);
}

export function formatTimestamp(value: string | null, timeZone: string): string {
  if (!value) {
    return "Not recorded yet";
  }
  void timeZone;
  return formatAppDateTime(value);
}

export function renderCheckpointRows(
  queue: GatewayAgentIntakeQueueSummary,
  timeZone: string,
): Array<[string, string]> {
  void timeZone;
  const { checkpoint } = queue;

  if (checkpoint.kind === "firehose") {
    return [
      ["Active mode", formatOptionalValue(checkpoint.active_mode)],
      ["Next page", formatOptionalValue(checkpoint.next_page)],
      ["Resume required", formatOptionalValue(checkpoint.resume_required)],
      ["New anchor", formatOptionalValue(checkpoint.new_anchor_date)],
      ["Trending anchor", formatOptionalValue(checkpoint.trending_anchor_date)],
      ["Run started", formatTimestamp(checkpoint.run_started_at, timeZone)],
      ["Last checkpoint", formatTimestamp(checkpoint.last_checkpointed_at, timeZone)],
      [
        "Mirror snapshot",
        formatTimestamp(checkpoint.mirror_snapshot_generated_at, timeZone),
      ],
    ];
  }

  return [
    ["Window start", formatOptionalValue(checkpoint.window_start_date)],
    [
      "Created before boundary",
      formatOptionalValue(checkpoint.created_before_boundary),
    ],
    [
      "Created before cursor",
      formatTimestamp(checkpoint.created_before_cursor, timeZone),
    ],
    ["Next page", formatOptionalValue(checkpoint.next_page)],
    ["Exhausted", formatOptionalValue(checkpoint.exhausted)],
    ["Last checkpoint", formatTimestamp(checkpoint.last_checkpointed_at, timeZone)],
    [
      "Mirror snapshot",
      formatTimestamp(checkpoint.mirror_snapshot_generated_at, timeZone),
    ],
  ];
}

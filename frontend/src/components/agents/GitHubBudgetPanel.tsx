"use client";

import type { GitHubApiBudgetSnapshot } from "@/lib/gateway-contract";

import { formatRelativeTimestamp, formatTimestampLabel } from "./agentPresentation";

function formatBudgetValue(value: number | null): string {
  if (value == null) {
    return "Unavailable";
  }
  return value.toLocaleString();
}

function deriveBudgetStatus(snapshot: GitHubApiBudgetSnapshot | null | undefined): {
  label: string;
  tone: string;
  guidance: string;
} {
  if (!snapshot) {
    return {
      label: "No budget data yet",
      tone: "var(--text-2)",
      guidance: "No GitHub response has been captured yet, so the shared GitHub quota is still unknown.",
    };
  }

  if (snapshot.exhausted || (snapshot.remaining ?? 1) <= 0) {
    return {
      label: "Quota exhausted",
      tone: "var(--red)",
      guidance:
        snapshot.reset_at != null
          ? `GitHub quota is exhausted. Wait until about ${formatTimestampLabel(snapshot.reset_at)}, then resume only one GitHub-heavy agent first.`
          : "GitHub quota is exhausted. Wait before resuming GitHub-heavy agents, then bring back one agent first.",
    };
  }

  if (snapshot.limit != null && snapshot.remaining != null) {
    const remainingRatio = snapshot.limit > 0 ? snapshot.remaining / snapshot.limit : 0;
    if (remainingRatio <= 0.1 || snapshot.remaining <= 250) {
      return {
        label: "Low quota",
        tone: "var(--amber)",
        guidance:
          "GitHub budget is getting tight. Prefer one intake agent at a time and avoid repeated manual reruns until the budget resets.",
      };
    }
  }

  return {
    label: "Quota healthy",
    tone: "var(--green)",
    guidance:
      "GitHub budget looks healthy right now. You can usually run one GitHub-heavy agent safely while continuing to monitor this card.",
  };
}

export function GitHubBudgetPanel({
  snapshot,
  title = "GitHub API Budget",
}: {
  snapshot: GitHubApiBudgetSnapshot | null | undefined;
  title?: string;
}) {
  const status = deriveBudgetStatus(snapshot);
  const limit = snapshot?.limit ?? null;
  const remaining = snapshot?.remaining ?? null;
  const used = snapshot?.used ?? null;
  const percentRemaining =
    limit != null && remaining != null && limit > 0
      ? Math.max(0, Math.min(100, Math.round((remaining / limit) * 100)))
      : null;

  return (
    <section
      className="card"
      style={{
        marginBottom: "16px",
        borderColor: status.tone,
        background: "color-mix(in srgb, var(--bg-0) 84%, var(--bg-3))",
      }}
    >
      <div className="card-header">
        <div>
          <div className="card-title">{title}</div>
          <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
            Shared quota from the latest GitHub API response seen by any worker.
          </div>
        </div>
        <div className="badge" style={{ borderColor: status.tone, color: status.tone }}>
          {status.label}
        </div>
      </div>

      <div style={{ display: "grid", gap: "12px", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
        <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
          <div className="card-label">Remaining</div>
          <div style={{ color: "var(--text-0)", fontSize: "22px", marginTop: "6px" }}>
            {formatBudgetValue(remaining)}
          </div>
          <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
            {limit != null ? `${percentRemaining ?? 0}% of ${formatBudgetValue(limit)}` : "Limit unavailable"}
          </div>
        </div>
        <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
          <div className="card-label">Used</div>
          <div style={{ color: "var(--text-0)", fontSize: "22px", marginTop: "6px" }}>
            {formatBudgetValue(used)}
          </div>
          <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
            Resource: {snapshot?.resource ?? "Unknown"}
          </div>
        </div>
        <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
          <div className="card-label">Reset At</div>
          <div style={{ color: "var(--text-0)", marginTop: "6px", lineHeight: 1.5 }}>
            {snapshot?.reset_at ? formatTimestampLabel(snapshot.reset_at) : "Unavailable"}
          </div>
          <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
            {snapshot?.reset_at ? formatRelativeTimestamp(snapshot.reset_at) : "No reset timestamp from GitHub"}
          </div>
        </div>
        <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
          <div className="card-label">Last Seen</div>
          <div style={{ color: "var(--text-0)", marginTop: "6px", lineHeight: 1.5 }}>
            {snapshot?.captured_at ? formatRelativeTimestamp(snapshot.captured_at) : "No snapshot yet"}
          </div>
          <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
            HTTP {snapshot?.last_response_status ?? "?"}
          </div>
        </div>
      </div>

      <div
        style={{
          marginTop: "12px",
          background: "var(--bg-3)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "12px",
        }}
      >
        <div className="card-label">Operator Guidance</div>
        <div style={{ color: "var(--text-0)", marginTop: "6px", lineHeight: 1.6 }}>{status.guidance}</div>
        {snapshot?.request_url ? (
          <div style={{ color: "var(--text-2)", marginTop: "6px", fontSize: "12px" }}>
            Latest request: {snapshot.request_url}
          </div>
        ) : null}
      </div>
    </section>
  );
}

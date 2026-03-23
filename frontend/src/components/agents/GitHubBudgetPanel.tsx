"use client";

import type {
  GitHubApiBudgetSnapshot,
  GitHubTokenBudgetSnapshot,
  GitHubTokenResourceBudgetSnapshot,
} from "@/lib/gateway-contract";

import { formatRelativeTimestamp, formatTimestampLabel } from "./agentPresentation";

function formatBudgetValue(value: number | null): string {
  if (value == null) {
    return "Unavailable";
  }
  return value.toLocaleString();
}

function formatSecondsLabel(value: number | null | undefined): string {
  if (value == null) {
    return "Unavailable";
  }
  if (value === 0) {
    return "0s";
  }
  if (value < 1) {
    return `${value.toFixed(2)}s`;
  }
  return `${Math.round(value)}s`;
}

function computeCombinedTokenCapacity(tokens: GitHubTokenBudgetSnapshot[] | undefined): {
  totalLimit: number | null;
  totalRemaining: number | null;
  observedTokens: number;
  configuredTokens: number;
} {
  if (!tokens?.length) {
    return { totalLimit: null, totalRemaining: null, observedTokens: 0, configuredTokens: 0 };
  }
  let limitKnown = false;
  let remainingKnown = false;
  let totalLimit = 0;
  let totalRemaining = 0;
  let observedTokens = 0;
  for (const token of tokens) {
    if (token.limit != null) {
      limitKnown = true;
      totalLimit += token.limit;
      observedTokens += 1;
    }
    if (token.remaining != null) {
      remainingKnown = true;
      totalRemaining += token.remaining;
    }
  }
  return {
    totalLimit: limitKnown ? totalLimit : null,
    totalRemaining: remainingKnown ? totalRemaining : null,
    observedTokens,
    configuredTokens: tokens.length,
  };
}

function isSnapshotStale(snapshot: GitHubApiBudgetSnapshot | null | undefined): boolean {
  if (!snapshot?.captured_at) {
    return false;
  }
  const capturedAt = Date.parse(snapshot.captured_at);
  if (Number.isNaN(capturedAt)) {
    return false;
  }
  return Date.now() - capturedAt > 10 * 60 * 1000;
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

  if (isSnapshotStale(snapshot)) {
    return {
      label: "Last known budget",
      tone: "var(--text-2)",
      guidance:
        snapshot.reset_at != null && Date.parse(snapshot.reset_at) <= Date.now()
          ? "This quota snapshot is older than the last reset window. Treat it as historical until a new GitHub response refreshes it."
          : "This card is showing the last captured GitHub quota snapshot. It is not proof that requests are happening right now.",
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

function formatTokenStatus(token: GitHubTokenBudgetSnapshot): {
  label: string;
  tone: string;
  guidance: string;
} {
  if (token.exhausted || (token.remaining ?? 1) <= 0) {
    return {
      label: "Exhausted",
      tone: "var(--red)",
      guidance:
        token.reset_at != null
          ? `This token is exhausted. It should cool down until about ${formatTimestampLabel(token.reset_at)}.`
          : "This token is exhausted. Wait for GitHub to reset it before relying on it again.",
    };
  }

  if (token.limit != null && token.remaining != null) {
    const ratio = token.limit > 0 ? token.remaining / token.limit : 0;
    if (ratio <= 0.1 || token.remaining <= 250) {
      return {
        label: "Low",
        tone: "var(--amber)",
        guidance: "This token is still usable, but it is getting tight. Prefer other healthy tokens first.",
      };
    }
  }

  return {
    label: "Healthy",
    tone: "var(--green)",
    guidance: "This token currently looks healthy enough for GitHub work.",
  };
}

function renderResourceBudget(resource: GitHubTokenResourceBudgetSnapshot) {
  return (
    <div
      key={resource.resource}
      style={{
        background: "var(--bg-3)",
        border: "1px solid var(--border)",
        borderRadius: "8px",
        padding: "10px",
      }}
    >
      <div className="card-label" style={{ textTransform: "capitalize" }}>
        {resource.resource}
      </div>
      <div style={{ color: "var(--text-0)", marginTop: "6px" }}>
        {formatBudgetValue(resource.remaining)} / {formatBudgetValue(resource.limit)}
      </div>
      <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
        Reset: {resource.reset_at ? formatTimestampLabel(resource.reset_at) : "Unavailable"}
      </div>
    </div>
  );
}

export function GitHubBudgetPanel({
  snapshot,
  title = "GitHub API Budget",
}: {
  snapshot: GitHubApiBudgetSnapshot | null | undefined;
  title?: string;
}) {
  const status = deriveBudgetStatus(snapshot);
  const stale = isSnapshotStale(snapshot);
  const limit = snapshot?.limit ?? null;
  const remaining = snapshot?.remaining ?? null;
  const used = snapshot?.used ?? null;
  const combinedCapacity = computeCombinedTokenCapacity(snapshot?.tokens);
  const scheduler = snapshot?.scheduler ?? null;
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
            Shared GitHub budget summary plus per-token health from the latest responses seen by the workers.
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
          <div className="card-label">Pool Capacity</div>
          <div style={{ color: "var(--text-0)", fontSize: "22px", marginTop: "6px" }}>
            {formatBudgetValue(combinedCapacity.totalRemaining)}
          </div>
          <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
            {combinedCapacity.configuredTokens === 0
              ? "Waiting for token observations"
              : combinedCapacity.totalLimit != null
                ? combinedCapacity.observedTokens < combinedCapacity.configuredTokens
                  ? `${combinedCapacity.observedTokens} of ${combinedCapacity.configuredTokens} tokens observed / ${formatBudgetValue(combinedCapacity.totalLimit)} observed budget`
                  : `Across ${combinedCapacity.configuredTokens} tokens / ${formatBudgetValue(combinedCapacity.totalLimit)} total`
                : `${combinedCapacity.configuredTokens} tokens configured, waiting for observed limits`}
          </div>
        </div>
        <div style={{ background: "var(--bg-3)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px" }}>
          <div className="card-label">Scheduler</div>
          <div style={{ color: "var(--text-0)", fontSize: "22px", marginTop: "6px" }}>
            {scheduler ? `${scheduler.active_requests} active` : "Unavailable"}
          </div>
          <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
            {scheduler
              ? `${scheduler.configured_tokens} tokens · search pace ${formatSecondsLabel(scheduler.search_min_interval_seconds)} · core pace ${formatSecondsLabel(scheduler.core_min_interval_seconds)}`
              : "No scheduler snapshot yet"}
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
        {stale ? (
          <div style={{ color: "var(--text-2)", marginTop: "6px", fontSize: "12px" }}>
            No recent GitHub response has refreshed this card, so use it as last-known quota state only.
          </div>
        ) : null}
        {snapshot?.request_url ? (
          <div style={{ color: "var(--text-2)", marginTop: "6px", fontSize: "12px" }}>
            Latest request: {snapshot.request_url}
          </div>
        ) : null}
      </div>

      {snapshot?.tokens?.length ? (
        <div style={{ marginTop: "12px" }}>
          <div className="card-label" style={{ marginBottom: "8px" }}>
            Token Pool
          </div>
          <div style={{ display: "grid", gap: "12px", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
            {snapshot.tokens.map((token) => {
              const tokenStatus = formatTokenStatus(token);
              return (
                <section
                  key={token.label}
                  style={{
                    background: "var(--bg-2)",
                    border: "1px solid var(--border)",
                    borderRadius: "10px",
                    padding: "12px",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "center" }}>
                    <div>
                      <div className="card-title" style={{ fontSize: "14px" }}>
                        {token.label.replace("-", " ").replace(/\b\w/g, (match) => match.toUpperCase())}
                      </div>
                      <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
                        Last seen {formatRelativeTimestamp(token.captured_at)}
                      </div>
                    </div>
                    <div className="badge" style={{ borderColor: tokenStatus.tone, color: tokenStatus.tone }}>
                      {tokenStatus.label}
                    </div>
                  </div>

                  <div style={{ marginTop: "10px", display: "grid", gap: "10px", gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
                    <div>
                      <div className="card-label">Latest bucket</div>
                      <div style={{ color: "var(--text-0)", marginTop: "4px", textTransform: "capitalize" }}>
                        {token.resource ?? "Unknown"}
                      </div>
                    </div>
                    <div>
                      <div className="card-label">Latest status</div>
                      <div style={{ color: "var(--text-0)", marginTop: "4px" }}>
                        HTTP {token.last_response_status ?? "?"}
                      </div>
                    </div>
                    <div>
                      <div className="card-label">Remaining</div>
                      <div style={{ color: "var(--text-0)", marginTop: "4px" }}>
                        {formatBudgetValue(token.remaining)}
                      </div>
                    </div>
                    <div>
                      <div className="card-label">Lane state</div>
                      <div style={{ color: "var(--text-0)", marginTop: "4px" }}>
                        {token.in_flight > 0 ? `Active (${token.in_flight})` : "Idle"}
                      </div>
                    </div>
                    <div>
                      <div className="card-label">Reset</div>
                      <div style={{ color: "var(--text-0)", marginTop: "4px" }}>
                        {token.reset_at ? formatTimestampLabel(token.reset_at) : "Unavailable"}
                      </div>
                    </div>
                    <div>
                      <div className="card-label">Next slot</div>
                      <div style={{ color: "var(--text-0)", marginTop: "4px" }}>
                        {token.next_available_at ? formatRelativeTimestamp(token.next_available_at) : "Ready now"}
                      </div>
                    </div>
                  </div>

                  {token.resource_budgets.length ? (
                    <div style={{ marginTop: "12px", display: "grid", gap: "8px" }}>
                      <div className="card-label">Tracked buckets</div>
                      <div style={{ display: "grid", gap: "8px", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))" }}>
                        {token.resource_budgets.map(renderResourceBudget)}
                      </div>
                    </div>
                  ) : null}

                  <div style={{ color: "var(--text-2)", marginTop: "10px", fontSize: "12px", lineHeight: 1.5 }}>
                    {tokenStatus.guidance}
                  </div>
                  {token.cooldown_until ? (
                    <div style={{ color: "var(--text-2)", marginTop: "6px", fontSize: "12px" }}>
                      Cooling until {formatTimestampLabel(token.cooldown_until)}
                    </div>
                  ) : null}
                  {token.last_used_at ? (
                    <div style={{ color: "var(--text-2)", marginTop: "6px", fontSize: "12px" }}>
                      Last used {formatRelativeTimestamp(token.last_used_at)}
                    </div>
                  ) : null}
                  {token.limit == null && token.remaining == null ? (
                    <div style={{ color: "var(--text-2)", marginTop: "6px", fontSize: "12px" }}>
                      This token is configured, but GitHub has not returned a quota observation for it yet in this runtime.
                    </div>
                  ) : null}
                </section>
              );
            })}
          </div>
        </div>
      ) : null}
    </section>
  );
}

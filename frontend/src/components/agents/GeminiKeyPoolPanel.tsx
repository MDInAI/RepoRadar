"use client";

import type { GeminiApiKeyPoolSnapshot } from "@/lib/gateway-contract";

import { formatRelativeTimestamp, formatTimestampLabel } from "./agentPresentation";

function toneForStatus(status: string): string {
  switch (status) {
    case "daily-limit":
      return "var(--red)";
    case "rate-limited":
      return "var(--amber)";
    case "healthy":
      return "var(--green)";
    case "auth-error":
      return "var(--red)";
    default:
      return "var(--text-2)";
  }
}

export function GeminiKeyPoolPanel({
  snapshot,
  title = "Gemini Analyst Key Pool",
}: {
  snapshot: GeminiApiKeyPoolSnapshot | null | undefined;
  title?: string;
}) {
  if (!snapshot) {
    return null;
  }

  return (
    <section className="card" style={{ marginBottom: "16px" }}>
      <div className="card-header">
        <div>
          <div className="card-title">{title}</div>
          <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
            Shared Haimaker/Gemini-compatible key pool for Analyst rotation and cooldown handling.
          </div>
        </div>
        <div className="badge">{snapshot.keys.length} keys</div>
      </div>

      <div style={{ color: "var(--text-2)", fontSize: "12px", marginBottom: "12px" }}>
        Model: {snapshot.model_name ?? "Unknown"} · Last updated{" "}
        {snapshot.captured_at ? formatRelativeTimestamp(snapshot.captured_at) : "unknown"}
      </div>

      <div style={{ display: "grid", gap: "12px", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
        {snapshot.keys.map((key) => (
          <section
            key={key.label}
            style={{
              background: "var(--bg-2)",
              border: "1px solid var(--border)",
              borderRadius: "10px",
              padding: "12px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "center" }}>
              <div className="card-title" style={{ fontSize: "14px" }}>
                {key.label.replace("-", " ").replace(/\b\w/g, (match) => match.toUpperCase())}
              </div>
              <div className="badge" style={{ borderColor: toneForStatus(key.status), color: toneForStatus(key.status) }}>
                {key.status}
              </div>
            </div>

            <div style={{ marginTop: "10px", display: "grid", gap: "10px", gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
              <div>
                <div className="card-label">Last used</div>
                <div style={{ color: "var(--text-0)", marginTop: "4px" }}>
                  {key.last_used_at ? formatRelativeTimestamp(key.last_used_at) : "Not yet"}
                </div>
              </div>
              <div>
                <div className="card-label">HTTP</div>
                <div style={{ color: "var(--text-0)", marginTop: "4px" }}>
                  {key.last_response_status ?? "?"}
                </div>
              </div>
              <div style={{ gridColumn: "1 / -1" }}>
                <div className="card-label">Cooldown until</div>
                <div style={{ color: "var(--text-0)", marginTop: "4px" }}>
                  {key.cooldown_until ? formatTimestampLabel(key.cooldown_until) : "None"}
                </div>
              </div>
            </div>

            {key.last_error ? (
              <div style={{ color: "var(--text-2)", marginTop: "10px", fontSize: "12px", lineHeight: 1.5 }}>
                {key.last_error}
              </div>
            ) : null}
          </section>
        ))}
      </div>
    </section>
  );
}

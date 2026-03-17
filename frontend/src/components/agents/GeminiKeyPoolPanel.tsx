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

function labelForStatus(status: string): string {
  switch (status) {
    case "daily-limit":
      return "Daily limit";
    case "rate-limited":
      return "Cooling down";
    case "healthy":
      return "Healthy";
    case "auth-error":
      return "Auth error";
    case "idle":
      return "Idle";
    default:
      return status;
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

  const healthyCount = snapshot.keys.filter((key) => key.status === "healthy").length;
  const coolingDownCount = snapshot.keys.filter(
    (key) => key.status === "rate-limited" || key.status === "daily-limit",
  ).length;
  const authErrorCount = snapshot.keys.filter((key) => key.status === "auth-error").length;
  const idleCount = snapshot.keys.filter((key) => key.status === "idle").length;

  return (
    <section className="card" style={{ marginBottom: "16px" }}>
      <div className="card-header">
        <div>
          <div className="card-title">{title}</div>
          <div style={{ color: "var(--text-2)", fontSize: "12px", marginTop: "4px" }}>
            Shared Haimaker/Gemini-compatible key pool for Analyst rotation and cooldown handling.
          </div>
        </div>
        <div className="badge">{snapshot.keys.length} keys configured</div>
      </div>

      <div style={{ color: "var(--text-2)", fontSize: "12px", marginBottom: "12px" }}>
        Model: {snapshot.model_name ?? "Unknown"} · Last updated{" "}
        {snapshot.captured_at ? formatRelativeTimestamp(snapshot.captured_at) : "unknown"}
      </div>

      <div
        style={{
          display: "grid",
          gap: "10px",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          marginBottom: "14px",
        }}
      >
        <section
          style={{
            background: "linear-gradient(180deg, rgba(56, 193, 114, 0.12), rgba(56, 193, 114, 0.04))",
            border: "1px solid rgba(56, 193, 114, 0.22)",
            borderRadius: "12px",
            padding: "12px",
          }}
        >
          <div className="card-label">Healthy</div>
          <div style={{ color: "var(--text-0)", fontSize: "22px", fontWeight: 700, marginTop: "6px" }}>
            {healthyCount}
          </div>
        </section>
        <section
          style={{
            background: "linear-gradient(180deg, rgba(201, 139, 27, 0.12), rgba(201, 139, 27, 0.04))",
            border: "1px solid rgba(201, 139, 27, 0.22)",
            borderRadius: "12px",
            padding: "12px",
          }}
        >
          <div className="card-label">Cooling Down</div>
          <div style={{ color: "var(--text-0)", fontSize: "22px", fontWeight: 700, marginTop: "6px" }}>
            {coolingDownCount}
          </div>
        </section>
        <section
          style={{
            background: "linear-gradient(180deg, rgba(120, 120, 120, 0.14), rgba(120, 120, 120, 0.05))",
            border: "1px solid rgba(120, 120, 120, 0.22)",
            borderRadius: "12px",
            padding: "12px",
          }}
        >
          <div className="card-label">Idle</div>
          <div style={{ color: "var(--text-0)", fontSize: "22px", fontWeight: 700, marginTop: "6px" }}>
            {idleCount}
          </div>
        </section>
        <section
          style={{
            background: "linear-gradient(180deg, rgba(217, 79, 79, 0.12), rgba(217, 79, 79, 0.04))",
            border: "1px solid rgba(217, 79, 79, 0.22)",
            borderRadius: "12px",
            padding: "12px",
          }}
        >
          <div className="card-label">Needs Fix</div>
          <div style={{ color: "var(--text-0)", fontSize: "22px", fontWeight: 700, marginTop: "6px" }}>
            {authErrorCount}
          </div>
        </section>
      </div>

      <div style={{ display: "grid", gap: "12px", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
        {snapshot.keys.map((key) => (
          <section
            key={key.label}
            style={{
              background:
                key.status === "healthy"
                  ? "linear-gradient(180deg, rgba(56, 193, 114, 0.10), rgba(56, 193, 114, 0.03))"
                  : key.status === "rate-limited" || key.status === "daily-limit"
                    ? "linear-gradient(180deg, rgba(201, 139, 27, 0.10), rgba(201, 139, 27, 0.03))"
                    : key.status === "auth-error"
                      ? "linear-gradient(180deg, rgba(217, 79, 79, 0.10), rgba(217, 79, 79, 0.03))"
                      : "var(--bg-2)",
              border: `1px solid ${
                key.status === "healthy"
                  ? "rgba(56, 193, 114, 0.20)"
                  : key.status === "rate-limited" || key.status === "daily-limit"
                    ? "rgba(201, 139, 27, 0.20)"
                    : key.status === "auth-error"
                      ? "rgba(217, 79, 79, 0.20)"
                      : "var(--border)"
              }`,
              borderRadius: "12px",
              padding: "14px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "center" }}>
              <div className="card-title" style={{ fontSize: "14px" }}>
                {key.label.replace("-", " ").replace(/\b\w/g, (match) => match.toUpperCase())}
              </div>
              <div className="badge" style={{ borderColor: toneForStatus(key.status), color: toneForStatus(key.status) }}>
                {labelForStatus(key.status)}
              </div>
            </div>

            <div
              style={{
                marginTop: "12px",
                display: "grid",
                gap: "10px",
                gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
              }}
            >
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
              <div
                style={{
                  color: "var(--text-2)",
                  marginTop: "12px",
                  fontSize: "12px",
                  lineHeight: 1.5,
                  paddingTop: "10px",
                  borderTop: "1px solid rgba(255,255,255,0.06)",
                }}
              >
                {key.last_error}
              </div>
            ) : null}
          </section>
        ))}
      </div>
    </section>
  );
}

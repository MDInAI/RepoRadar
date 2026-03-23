"use client";

import type { AgentPauseState, AgentStatusEntry } from "@/api/agents";
import { isAgentEffectivelyRunning } from "@/components/agents/alertState";
import {
  formatAgentName,
  formatRuntimeProgressCounts,
  formatRuntimeProgressHeadline,
  formatItemsSummary,
} from "@/components/agents/agentPresentation";

interface PipelineStage {
  name: string;
  agentName: string | null;
  count: number;
  label: string;
}

function getAgentStatus(
  agentName: string | null,
  agents: AgentStatusEntry[],
  pauseStates: AgentPauseState[],
): { status: "running" | "paused" | "idle" | "failed" | "none"; badge: string; badgeClass: string } {
  if (!agentName) return { status: "none", badge: "—", badgeClass: "badge badge-muted" };

  const entry = agents.find((a) => a.agent_name === agentName);
  const pause = pauseStates.find((p) => p.agent_name === agentName);

  if (pause?.is_paused) return { status: "paused", badge: "Paused", badgeClass: "badge badge-red" };
  if (entry && isAgentEffectivelyRunning(entry, pause)) return { status: "running", badge: "Running", badgeClass: "badge badge-yellow" };
  if (entry?.latest_run?.status === "failed") return { status: "failed", badge: "Failed", badgeClass: "badge badge-red" };
  return { status: "idle", badge: "Idle", badgeClass: "badge badge-green" };
}

function getProgressSummary(agentName: string | null, agents: AgentStatusEntry[]): string {
  if (!agentName) return "";
  const entry = agents.find((a) => a.agent_name === agentName);
  if (!entry) return "";
  return formatRuntimeProgressHeadline(entry.runtime_progress) || formatItemsSummary(entry.latest_run) || "";
}

function getProgressPercent(agentName: string | null, agents: AgentStatusEntry[]): number | null {
  if (!agentName) return null;
  const entry = agents.find((a) => a.agent_name === agentName);
  return entry?.runtime_progress?.progress_percent ?? null;
}

export function PipelineStrip({
  stages,
  agents,
  pauseStates,
}: {
  stages: PipelineStage[];
  agents: AgentStatusEntry[];
  pauseStates: AgentPauseState[];
}) {
  return (
    <div className="pipeline-strip">
      {stages.map((stage, i) => {
        const agentStatus = getAgentStatus(stage.agentName, agents, pauseStates);
        const progress = getProgressSummary(stage.agentName, agents);
        const progressPercent = getProgressPercent(stage.agentName, agents);
        const nodeClass = [
          "pipeline-node",
          agentStatus.status === "running" ? "pipeline-node-active" : "",
          agentStatus.status === "paused" ? "pipeline-node-paused" : "",
        ].join(" ").trim();

        return (
          <div key={stage.name} className="pipeline-stage-wrap">
            {i > 0 && (
              <div className="pipeline-arrow">→</div>
            )}
            <div className={nodeClass}>
              <div className="pipeline-node-name">{stage.name}</div>
              <div className="pipeline-node-count" style={{
                color: stage.count > 0
                  ? agentStatus.status === "running" ? "var(--amber)" : "var(--text-0)"
                  : "var(--text-3)"
              }}>
                {stage.count.toLocaleString()}
              </div>
              <div className="pipeline-node-label">{stage.label}</div>

              {stage.agentName && (
                <div className="pipeline-node-agent">
                  <span className={agentStatus.badgeClass} style={{ fontSize: "9px" }}>
                    {agentStatus.badge}
                  </span>
                  {progress && (
                    <div style={{ fontSize: "10px", color: "var(--text-2)", textAlign: "center", lineHeight: 1.3, marginTop: "2px" }}>
                      {progress}
                    </div>
                  )}
                  {progressPercent != null && (
                    <div className="progress" style={{ width: "100%", marginTop: "4px" }}>
                      <div
                        className="progress-bar"
                        style={{
                          width: `${Math.max(0, Math.min(progressPercent, 100))}%`,
                          background: agentStatus.status === "running" ? "var(--amber)" : "var(--green)",
                        }}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

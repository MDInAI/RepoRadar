"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchAgentPauseStates,
  pauseAgent,
  resumeAgent,
  getAgentPauseStatesQueryKey,
  type AgentName
} from "@/api/agents";

export default function ControlPanel() {
  const [selectedAgent, setSelectedAgent] = useState<AgentName>("firehose");
  const queryClient = useQueryClient();

  const { data: pauseStates } = useQuery({
    queryKey: getAgentPauseStatesQueryKey(),
    queryFn: fetchAgentPauseStates,
    refetchInterval: 5000,
  });

  const pauseMutation = useMutation({
    mutationFn: ({ agent, reason }: { agent: AgentName; reason: string }) =>
      pauseAgent(agent, reason, "manual"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: getAgentPauseStatesQueryKey() });
    },
  });

  const resumeMutation = useMutation({
    mutationFn: (agent: AgentName) => resumeAgent(agent),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: getAgentPauseStatesQueryKey() });
    },
  });

  const agents: Array<{ id: AgentName; label: string; icon: string; desc: string; usesAI: boolean }> = [
    { id: "overlord", label: "Overlord", icon: "👑", desc: "System monitor", usesAI: false },
    { id: "firehose", label: "Firehose", icon: "🔥", desc: "Real-time discovery", usesAI: false },
    { id: "backfill", label: "Backfill", icon: "⏮️", desc: "Historical processing", usesAI: false },
    { id: "bouncer", label: "Bouncer", icon: "🚪", desc: "Repository filtering", usesAI: false },
    { id: "analyst", label: "Analyst", icon: "🔬", desc: "AI-powered analysis", usesAI: true },
  ];

  const currentAgent = agents.find(a => a.id === selectedAgent);
  const agentPauseState = pauseStates?.find(s => s.agent_name === selectedAgent);
  const isPaused = agentPauseState?.is_paused || false;

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Control Panel</span>
        <span className="topbar-breadcrumb">agent control</span>
      </div>

      <div style={{ display: 'flex', height: 'calc(100vh - 44px)' }}>
        <div style={{ width: '240px', background: 'var(--bg-1)', borderRight: '1px solid var(--border)', padding: '16px' }}>
          <div className="card-label" style={{ marginBottom: '12px' }}>
            Agents
          </div>
          {agents.map((agent) => {
            const state = pauseStates?.find(s => s.agent_name === agent.id);
            return (
              <AgentBtn
                key={agent.id}
                agent={agent}
                active={selectedAgent === agent.id}
                paused={state?.is_paused || false}
                onClick={() => setSelectedAgent(agent.id)}
              />
            );
          })}
        </div>

        <div style={{ flex: 1, padding: '24px', overflow: 'auto' }}>
          <div style={{ maxWidth: '900px' }}>
            <div className="card" style={{ marginBottom: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
                <div>
                  <h2 style={{ fontSize: '20px', fontWeight: 600, color: 'var(--text-0)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span>{currentAgent?.icon}</span>
                    <span>{currentAgent?.label}</span>
                    {currentAgent?.usesAI && <span className="badge badge-blue">AI Agent</span>}
                  </h2>
                  <div style={{ fontSize: '12px', color: 'var(--text-2)', marginTop: '4px' }}>
                    {currentAgent?.desc}
                  </div>
                </div>
                <span className={`badge ${isPaused ? 'badge-red' : 'badge-green'}`}>
                  {isPaused ? 'Paused' : 'Active'}
                </span>
              </div>

              <div style={{ display: 'flex', gap: '8px' }}>
                {isPaused ? (
                  <button
                    onClick={() => resumeMutation.mutate(selectedAgent)}
                    disabled={resumeMutation.isPending}
                    style={{
                      padding: '8px 16px',
                      background: 'var(--green)',
                      color: 'var(--bg-0)',
                      border: 'none',
                      borderRadius: '6px',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: resumeMutation.isPending ? 'wait' : 'pointer',
                      opacity: resumeMutation.isPending ? 0.6 : 1
                    }}
                  >
                    ▶ Resume Agent
                  </button>
                ) : (
                  <button
                    onClick={() => pauseMutation.mutate({ agent: selectedAgent, reason: "Manual pause from control panel" })}
                    disabled={pauseMutation.isPending}
                    style={{
                      padding: '8px 16px',
                      background: 'var(--yellow)',
                      color: 'var(--bg-0)',
                      border: 'none',
                      borderRadius: '6px',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: pauseMutation.isPending ? 'wait' : 'pointer',
                      opacity: pauseMutation.isPending ? 0.6 : 1
                    }}
                  >
                    ⏸ Pause Agent
                  </button>
                )}
              </div>

              {agentPauseState?.paused_at && (
                <div style={{
                  marginTop: '16px',
                  padding: '12px',
                  background: 'var(--bg-3)',
                  border: '1px solid var(--border)',
                  borderRadius: '6px',
                  fontSize: '11px',
                  color: 'var(--text-2)'
                }}>
                  <div><strong style={{ color: 'var(--text-0)' }}>Paused at:</strong> {new Date(agentPauseState.paused_at).toLocaleString()}</div>
                  {agentPauseState.pause_reason && (
                    <div style={{ marginTop: '4px' }}><strong style={{ color: 'var(--text-0)' }}>Reason:</strong> {agentPauseState.pause_reason}</div>
                  )}
                </div>
              )}
            </div>

            {selectedAgent === "analyst" && <AnalystConfig />}
            {selectedAgent === "firehose" && <FirehoseConfig />}
            {selectedAgent === "backfill" && <BackfillConfig />}
            {selectedAgent === "bouncer" && <BouncerConfig />}
            {selectedAgent === "overlord" && <OverlordConfig />}
          </div>
        </div>
      </div>
    </>
  );
}

function AgentBtn({ agent, active, paused, onClick }: any) {
  return (
    <button onClick={onClick} style={{
      width: '100%',
      padding: '12px',
      background: active ? 'var(--amber-dim)' : 'transparent',
      color: active ? 'var(--amber)' : 'var(--text-2)',
      border: 'none',
      borderRadius: '6px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      cursor: 'pointer',
      marginBottom: '4px',
      fontSize: '13px',
      fontWeight: 500
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span>{agent.icon}</span>
        <span>{agent.label}</span>
      </div>
      {paused && <span style={{ fontSize: '10px', color: 'var(--red)' }}>●</span>}
    </button>
  );
}

function ConfigPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card" style={{ marginBottom: '16px' }}>
      <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-0)', marginBottom: '12px' }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function EditableRow({ label, value, unit, onChange }: { label: string; value: string | number; unit?: string; onChange?: (val: string) => void }) {
  const [editing, setEditing] = React.useState(false);
  const [editValue, setEditValue] = React.useState(String(value));

  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ fontSize: '12px', color: 'var(--text-2)' }}>{label}</span>
      {editing && onChange ? (
        <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
          <input
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            style={{
              padding: '4px 8px',
              background: 'var(--bg-3)',
              border: '1px solid var(--border)',
              borderRadius: '4px',
              color: 'var(--text-0)',
              fontSize: '11px',
              fontFamily: 'var(--mono)',
              width: '100px'
            }}
          />
          <button
            onClick={() => {
              onChange(editValue);
              setEditing(false);
            }}
            style={{
              padding: '4px 8px',
              background: 'var(--green)',
              border: 'none',
              borderRadius: '4px',
              color: 'var(--bg-0)',
              fontSize: '10px',
              cursor: 'pointer'
            }}
          >
            ✓
          </button>
          <button
            onClick={() => {
              setEditValue(String(value));
              setEditing(false);
            }}
            style={{
              padding: '4px 8px',
              background: 'var(--bg-3)',
              border: '1px solid var(--border)',
              borderRadius: '4px',
              color: 'var(--text-2)',
              fontSize: '10px',
              cursor: 'pointer'
            }}
          >
            ✕
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-0)', fontFamily: 'var(--mono)' }}>
            {value}{unit && <span style={{ color: 'var(--text-3)', marginLeft: '4px' }}>{unit}</span>}
          </span>
          {onChange && (
            <button
              onClick={() => setEditing(true)}
              style={{
                padding: '2px 6px',
                background: 'transparent',
                border: '1px solid var(--border)',
                borderRadius: '4px',
                color: 'var(--text-3)',
                fontSize: '10px',
                cursor: 'pointer'
              }}
            >
              Edit
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function AnalystConfig() {
  const [model, setModel] = React.useState("Claude Opus 4");
  const [maxTokens, setMaxTokens] = React.useState("4000");
  const [temperature, setTemperature] = React.useState("0.3");

  return (
    <>
      <div style={{
        background: 'var(--blue-dim)',
        border: '1px solid var(--blue)',
        borderRadius: '10px',
        padding: '12px',
        marginBottom: '16px',
        fontSize: '12px',
        color: 'var(--text-1)'
      }}>
        <strong style={{ color: 'var(--blue)' }}>ℹ️ AI Agent:</strong> This agent uses Claude AI to analyze repositories and assess monetization potential. Changes to model settings affect analysis quality and cost.
      </div>

      <ConfigPanel title="AI Model Configuration">
        <EditableRow label="Model" value={model} onChange={setModel} />
        <EditableRow label="Max Tokens" value={maxTokens} onChange={setMaxTokens} />
        <EditableRow label="Temperature" value={temperature} onChange={setTemperature} />
        <EditableRow label="Provider" value="Anthropic" />
      </ConfigPanel>

      <ConfigPanel title="Queue & Performance">
        <EditableRow label="Pending" value={23} />
        <EditableRow label="In Progress" value={2} />
        <EditableRow label="Avg Time" value="45s" />
        <EditableRow label="Batch Size" value={10} onChange={(v) => console.log('Batch size:', v)} />
      </ConfigPanel>

      <ConfigPanel title="Token Usage (24h)">
        <EditableRow label="Total Tokens" value="1.8M" />
        <EditableRow label="Cost Estimate" value="$27.00" />
        <EditableRow label="Avg per Repo" value="~3,200 tokens" />
      </ConfigPanel>

      <ConfigPanel title="Analysis Settings">
        <EditableRow label="Min Stars Required" value={100} onChange={(v) => console.log('Min stars:', v)} />
        <EditableRow label="Retry Failed" value="Enabled" />
        <EditableRow label="Max Retries" value={3} onChange={(v) => console.log('Max retries:', v)} />
      </ConfigPanel>
    </>
  );
}

function FirehoseConfig() {
  return (
    <>
      <div style={{
        background: 'var(--bg-3)',
        border: '1px solid var(--border)',
        borderRadius: '10px',
        padding: '12px',
        marginBottom: '16px',
        fontSize: '12px',
        color: 'var(--text-2)'
      }}>
        <strong style={{ color: 'var(--text-0)' }}>ℹ️ Discovery Agent:</strong> Monitors GitHub for new and trending repositories in real-time. No AI model used.
      </div>

      <ConfigPanel title="Discovery Modes">
        <EditableRow label="NEW Mode" value="Enabled" onChange={(v) => console.log('NEW mode:', v)} />
        <EditableRow label="TRENDING Mode" value="Enabled" onChange={(v) => console.log('TRENDING mode:', v)} />
        <EditableRow label="Per Page" value={100} onChange={(v) => console.log('Per page:', v)} />
        <EditableRow label="Pages per Run" value={3} onChange={(v) => console.log('Pages:', v)} />
      </ConfigPanel>

      <ConfigPanel title="Timing">
        <EditableRow label="Interval" value={3600} unit="seconds" onChange={(v) => console.log('Interval:', v)} />
        <EditableRow label="Next Run" value="~45 min" />
      </ConfigPanel>

      <ConfigPanel title="Rate Limits">
        <EditableRow label="GitHub API Limit" value="5000/hour" />
        <EditableRow label="Current Usage" value="1,247/hour" />
        <EditableRow label="Headroom" value="75%" />
      </ConfigPanel>
    </>
  );
}

function BackfillConfig() {
  return (
    <>
      <div style={{
        background: 'var(--bg-3)',
        border: '1px solid var(--border)',
        borderRadius: '10px',
        padding: '12px',
        marginBottom: '16px',
        fontSize: '12px',
        color: 'var(--text-2)'
      }}>
        <strong style={{ color: 'var(--text-0)' }}>ℹ️ Historical Agent:</strong> Processes older repositories to build complete dataset. No AI model used.
      </div>

      <ConfigPanel title="Backfill Settings">
        <EditableRow label="Mode" value="Historical" />
        <EditableRow label="Start Date" value="2024-01-01" onChange={(v) => console.log('Start date:', v)} />
        <EditableRow label="Batch Size" value={50} onChange={(v) => console.log('Batch size:', v)} />
        <EditableRow label="Progress" value="87%" />
      </ConfigPanel>

      <ConfigPanel title="Timing">
        <EditableRow label="Interval" value={7200} unit="seconds" onChange={(v) => console.log('Interval:', v)} />
        <EditableRow label="Last Run" value="2h ago" />
      </ConfigPanel>

      <ConfigPanel title="Status">
        <EditableRow label="Repos Processed" value="4,872" />
        <EditableRow label="Remaining" value="~600" />
      </ConfigPanel>
    </>
  );
}

function BouncerConfig() {
  return (
    <>
      <div style={{
        background: 'var(--bg-3)',
        border: '1px solid var(--border)',
        borderRadius: '10px',
        padding: '12px',
        marginBottom: '16px',
        fontSize: '12px',
        color: 'var(--text-2)'
      }}>
        <strong style={{ color: 'var(--text-0)' }}>ℹ️ Filter Agent:</strong> Applies rules to filter repositories based on stars, forks, and activity. No AI model used.
      </div>

      <ConfigPanel title="Filter Rules">
        <EditableRow label="Min Stars" value={100} onChange={(v) => console.log('Min stars:', v)} />
        <EditableRow label="Min Forks" value={10} onChange={(v) => console.log('Min forks:', v)} />
        <EditableRow label="Active Maintenance" value="Required" onChange={(v) => console.log('Maintenance:', v)} />
        <EditableRow label="License Check" value="Enabled" onChange={(v) => console.log('License:', v)} />
      </ConfigPanel>

      <ConfigPanel title="Performance">
        <EditableRow label="Batch Size" value={50} onChange={(v) => console.log('Batch size:', v)} />
        <EditableRow label="Avg Processing Time" value="2.3s" />
      </ConfigPanel>

      <ConfigPanel title="Statistics (24h)">
        <EditableRow label="Processed" value={186} />
        <EditableRow label="Accepted" value={47} unit="(25%)" />
        <EditableRow label="Rejected" value={139} unit="(75%)" />
      </ConfigPanel>
    </>
  );
}

function OverlordConfig() {
  return (
    <>
      <div style={{
        background: 'var(--bg-3)',
        border: '1px solid var(--border)',
        borderRadius: '10px',
        padding: '12px',
        marginBottom: '16px',
        fontSize: '12px',
        color: 'var(--text-2)'
      }}>
        <strong style={{ color: 'var(--text-0)' }}>ℹ️ Monitor Agent:</strong> Watches all agents and triggers alerts on failures. No AI model used.
      </div>

      <ConfigPanel title="Monitoring">
        <EditableRow label="Check Interval" value={60} unit="seconds" onChange={(v) => console.log('Interval:', v)} />
        <EditableRow label="Alert Threshold" value="3 failures" onChange={(v) => console.log('Threshold:', v)} />
        <EditableRow label="Auto-Recovery" value="Enabled" onChange={(v) => console.log('Auto-recovery:', v)} />
      </ConfigPanel>

      <ConfigPanel title="System Health">
        <EditableRow label="All Agents" value="Operational" />
        <EditableRow label="Database" value="Healthy" />
        <EditableRow label="API Gateway" value="Connected" />
      </ConfigPanel>

      <ConfigPanel title="Alerts (24h)">
        <EditableRow label="Critical" value={0} />
        <EditableRow label="Warnings" value={3} />
        <EditableRow label="Info" value={47} />
      </ConfigPanel>
    </>
  );
}

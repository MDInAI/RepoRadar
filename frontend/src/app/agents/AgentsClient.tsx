"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  AGENT_DISPLAY_ORDER,
  fetchAgentPauseStates,
  fetchAgentRuns,
  fetchLatestAgentRuns,
  getAgentPauseStatesQueryKey,
  getAgentRunsQueryKey,
  getLatestAgentRunsQueryKey,
  type AgentName,
  type AgentRunStatus,
} from "@/api/agents";
import { AgentRunHistoryTable } from "@/components/agents/AgentRunHistoryTable";
import { PauseAgentButton } from "@/components/agents/PauseAgentButton";
import { ResumeAgentButton } from "@/components/agents/ResumeAgentButton";

const RUN_PAGE_SIZE = 50;
const MAX_RUN_PAGE_SIZE = 200;

export default function AgentsClient() {
  const [selectedAgent, setSelectedAgent] = useState<AgentName>("overlord");
  const [agentFilter, setAgentFilter] = useState<AgentName | null>(null);
  const [statusFilter, setStatusFilter] = useState<AgentRunStatus | null>(null);
  const [runLimit, setRunLimit] = useState(RUN_PAGE_SIZE);

  const latestRunsQuery = useQuery({
    queryKey: getLatestAgentRunsQueryKey(),
    queryFn: fetchLatestAgentRuns,
    staleTime: 30_000,
  });

  const pauseStatesQuery = useQuery({
    queryKey: getAgentPauseStatesQueryKey(),
    queryFn: fetchAgentPauseStates,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const runsQuery = useQuery({
    queryKey: getAgentRunsQueryKey({
      agent_name: agentFilter,
      status: statusFilter,
      limit: runLimit,
    }),
    queryFn: () =>
      fetchAgentRuns({
        agent_name: agentFilter,
        status: statusFilter,
        limit: runLimit,
      }),
  });

  const agents = latestRunsQuery.data?.agents ?? AGENT_DISPLAY_ORDER.map((agentName) => ({
    agent_name: agentName,
    display_name: agentName[0].toUpperCase() + agentName.slice(1),
    role_label: "Loading…",
    description: "",
    implementation_status: "loading",
    runtime_kind: "loading",
    uses_github_token: false,
    uses_model: false,
    configured_provider: null,
    configured_model: null,
    notes: [],
    token_usage_24h: 0,
    input_tokens_24h: 0,
    output_tokens_24h: 0,
    has_run: false,
    latest_run: null,
  }));

  const selectedAgentData = agents.find(a => a.agent_name === selectedAgent);
  const selectedPauseState = pauseStatesQuery.data?.find(p => p.agent_name === selectedAgent);
  const isPaused = selectedPauseState?.is_paused || false;

  const activeCount = latestRunsQuery.data?.agents.filter(a => {
    const paused = pauseStatesQuery.data?.find(p => p.agent_name === a.agent_name)?.is_paused;
    return !paused && a.latest_run && a.latest_run.status === 'completed';
  }).length || 0;

  const runningCount = latestRunsQuery.data?.agents.filter(a => {
    const paused = pauseStatesQuery.data?.find(p => p.agent_name === a.agent_name)?.is_paused;
    return !paused && a.latest_run && a.latest_run.status === 'running';
  }).length || 0;

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Agents</span>
        <span className="topbar-breadcrumb">management</span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
        <div className="hero-strip mb-16">
          <div>
            <h2>Agent Management</h2>
            <div className="sub">Monitor, control, and inspect all named agents</div>
          </div>
          <div className="flex items-center gap-8">
            <span className="badge badge-green">{activeCount} Active</span>
            <span className="badge badge-yellow">{runningCount} Running</span>
            <span className="badge badge-muted">0 Idle</span>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr 280px', gap: '16px' }}>
          <div className="flex flex-col gap-8">
            <div className="section-head"><span className="section-title">Roster</span></div>
            {agents.map((agent) => {
              const agentData = agent;
              const pauseState = pauseStatesQuery.data?.find(p => p.agent_name === agent.agent_name);
              const status = pauseState?.is_paused ? 'red' : agentData?.latest_run?.status === 'running' ? 'yellow' : 'green';

              return (
                <div
                  key={agent.agent_name}
                  className={`agent-card ${selectedAgent === agent.agent_name ? 'selected' : ''}`}
                  data-testid={`agent-roster-card-${agent.agent_name}`}
                  onClick={() => setSelectedAgent(agent.agent_name)}
                >
                  <div className="flex items-center justify-between">
                    <span className="agent-name">{agent.display_name}</span>
                    <span className={`badge badge-${status}`}>●</span>
                  </div>
                  <div className="agent-role">{agent.role_label}</div>
                </div>
              );
            })}
          </div>

          <div>
            <div className="card mb-12" data-testid="agent-details-panel">
              <div className="card-header">
                <span className="card-title">{selectedAgentData?.display_name ?? selectedAgent}</span>
                <span className={`badge ${isPaused ? 'badge-red' : 'badge-green'}`}>
                  {isPaused ? 'Paused' : 'Active'}
                </span>
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-2)', marginBottom: '12px' }}>
                {selectedAgentData?.role_label ?? "Loading role…"}
              </div>
              <div className="grid g4 mb-12">
                <div>
                  <div className="card-label">Last Run</div>
                  <div style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-0)', marginTop: '4px' }}>
                    {selectedAgentData?.latest_run ? new Date(selectedAgentData.latest_run.started_at).toLocaleTimeString() : '—'}
                  </div>
                </div>
                <div>
                  <div className="card-label">Items</div>
                  <div style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-0)', marginTop: '4px', fontFamily: 'var(--mono)' }}>
                    {selectedAgentData?.latest_run?.items_processed || 0}
                  </div>
                </div>
                <div>
                  <div className="card-label">Provider</div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--green)', marginTop: '4px', fontFamily: 'var(--mono)' }}>
                    {selectedAgentData?.latest_run?.provider_name ?? selectedAgentData?.configured_provider ?? "local-only"}
                  </div>
                </div>
                <div>
                  <div className="card-label">Model</div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-0)', marginTop: '4px', fontFamily: 'var(--mono)' }}>
                    {selectedAgentData?.latest_run?.model_name ?? selectedAgentData?.configured_model ?? "none"}
                  </div>
                </div>
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-2)', marginBottom: '12px', lineHeight: '1.6' }}>
                <div><span className="card-label">Runtime</span></div>
                <div style={{ marginTop: '4px' }}>{selectedAgentData?.description ?? "Loading runtime details…"}</div>
                <div style={{ marginTop: '8px', fontFamily: 'var(--mono)', fontSize: '11px', color: 'var(--text-3)' }}>
                  Kind: {selectedAgentData?.runtime_kind ?? "loading"} · Status: {selectedAgentData?.implementation_status ?? "loading"}
                </div>
                <div style={{ marginTop: '6px', fontFamily: 'var(--mono)', fontSize: '11px', color: 'var(--text-3)' }}>
                  GitHub token: {selectedAgentData?.uses_github_token ? "yes" : "no"} · Model-backed: {selectedAgentData?.uses_model ? "yes" : "no"}
                </div>
              </div>
              <div className="flex gap-8">
                {isPaused ? (
                  <ResumeAgentButton agentName={selectedAgent} />
                ) : (
                  <PauseAgentButton agentName={selectedAgent} />
                )}
              </div>
            </div>

            <div className="section-head"><span className="section-title">Logs</span><div className="section-line"></div></div>
            <div className="card mb-12" style={{ maxHeight: '200px', overflowY: 'auto' }}>
              <div style={{ fontSize: '11px', fontFamily: 'var(--mono)', color: 'var(--text-2)' }}>
                <div style={{ padding: '4px 0' }}>[{new Date().toLocaleTimeString()}] Agent cycle completed</div>
                <div style={{ padding: '4px 0' }}>[{new Date().toLocaleTimeString()}] Processing batch...</div>
                <div style={{ padding: '4px 0' }}>[{new Date().toLocaleTimeString()}] Health check passed</div>
              </div>
            </div>

            <div className="section-head"><span className="section-title">Throughput</span><div className="section-line"></div></div>
            <div className="card mb-12">
              <div className="grid g3">
                <div>
                  <div className="card-label">Avg/hour</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-0)', fontFamily: 'var(--mono)' }}>
                    {selectedAgentData?.latest_run?.items_processed || 0}
                  </div>
                </div>
                <div>
                  <div className="card-label">Peak/hour</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--amber)', fontFamily: 'var(--mono)' }}>
                    {(selectedAgentData?.latest_run?.items_processed || 0) * 1.5}
                  </div>
                </div>
                <div>
                  <div className="card-label">Success Rate</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--green)', fontFamily: 'var(--mono)' }}>
                    {selectedAgentData?.latest_run?.items_succeeded && selectedAgentData?.latest_run?.items_processed
                      ? Math.round((selectedAgentData.latest_run.items_succeeded / selectedAgentData.latest_run.items_processed) * 100)
                      : 0}%
                  </div>
                </div>
              </div>
            </div>

            <div className="section-head"><span className="section-title">Token Usage & Budget</span><div className="section-line"></div></div>
            <div className="card mb-12">
              <div style={{ fontSize: '12px', color: 'var(--text-2)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                  <span>Last 24h</span>
                  <span style={{ fontFamily: 'var(--mono)', color: 'var(--text-0)' }}>{formatTokenCount(selectedAgentData?.token_usage_24h || 0)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                  <span>Input</span>
                  <span style={{ fontFamily: 'var(--mono)', color: 'var(--green)' }}>{formatTokenCount(selectedAgentData?.input_tokens_24h || 0)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
                  <span>Output</span>
                  <span style={{ fontFamily: 'var(--mono)', color: 'var(--text-0)' }}>{formatTokenCount(selectedAgentData?.output_tokens_24h || 0)}</span>
                </div>
              </div>
              <div style={{ marginTop: '10px', fontSize: '11px', color: 'var(--text-3)', fontFamily: 'var(--mono)' }}>
                {selectedAgentData?.uses_model
                  ? `Latest provider: ${selectedAgentData?.latest_run?.provider_name ?? selectedAgentData?.configured_provider ?? "unknown"}`
                  : "No model-backed usage is expected for this agent in the current runtime."}
              </div>
            </div>

            <div className="section-head"><span className="section-title">Run History</span><div className="section-line"></div></div>
            {runsQuery.isError ? (
              <div className="card" style={{ background: 'var(--red-dim)', borderColor: 'var(--red)' }}>
                Unable to load run history
              </div>
            ) : (
              <AgentRunHistoryTable
                agentFilter={agentFilter}
                canLoadMore={!runsQuery.isLoading && runLimit < MAX_RUN_PAGE_SIZE && (runsQuery.data?.length ?? 0) >= runLimit}
                isLoading={runsQuery.isLoading}
                isLoadingMore={runsQuery.isFetching && !runsQuery.isLoading}
                onAgentFilterChange={setAgentFilter}
                onLoadMore={() => setRunLimit((limit) => Math.min(limit + RUN_PAGE_SIZE, MAX_RUN_PAGE_SIZE))}
                onStatusFilterChange={setStatusFilter}
                runs={runsQuery.data ?? []}
                statusFilter={statusFilter}
              />
            )}
          </div>

          <div>
            <div className="section-head"><span className="section-title">Controls</span></div>
            <div className="card mb-12">
              <div className="flex gap-8" style={{ flexDirection: 'column' }}>
                {isPaused ? (
                  <ResumeAgentButton agentName={selectedAgent} />
                ) : (
                  <PauseAgentButton agentName={selectedAgent} />
                )}
                <button className="btn btn-sm">View Logs</button>
                <button className="btn btn-sm">Adjust Rate</button>
              </div>
            </div>

            <div className="section-head"><span className="section-title">Schedule</span></div>
            <div className="card mb-12">
              <div style={{ fontSize: '12px', color: 'var(--text-2)' }}>
                <div style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>Next run: 15 min</div>
                <div style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>Interval: 1h</div>
                <div style={{ padding: '8px 0' }}>Last: 45 min ago</div>
              </div>
            </div>

            <div className="section-head"><span className="section-title">Anomalies</span></div>
            <div className="card mb-12">
              <div style={{ fontSize: '12px', color: 'var(--text-2)', lineHeight: '1.6' }}>
                {selectedAgentData?.notes?.length
                  ? selectedAgentData.notes.map((note, index) => <div key={index} style={{ padding: '6px 0' }}>{note}</div>)
                  : <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: '20px' }}>No anomalies detected</div>}
              </div>
            </div>

            <div className="section-head"><span className="section-title">Console</span></div>
            <div className="card" style={{ background: 'var(--bg-3)', fontFamily: 'var(--mono)', fontSize: '10px', color: 'var(--text-3)', padding: '12px', maxHeight: '150px', overflowY: 'auto' }}>
              <div>$ agent status {selectedAgent}</div>
              <div>✓ healthy</div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function formatTokenCount(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return `${value}`;
}

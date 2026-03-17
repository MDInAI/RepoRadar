"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import {
  fetchLatestAgentRuns,
  fetchAgentPauseStates,
  fetchFailureEvents,
  getLatestAgentRunsQueryKey,
  getAgentPauseStatesQueryKey,
  getFailureEventsQueryKey,
} from "@/api/agents";
import { fetchOverviewSummary, getOverviewSummaryQueryKey } from "@/api/overview";
import { fetchGatewayRuntime } from "@/api/readiness";
import { GeminiKeyPoolPanel } from "@/components/agents/GeminiKeyPoolPanel";
import { GitHubBudgetPanel } from "@/components/agents/GitHubBudgetPanel";
import { AgentOperatorSummary } from "@/components/agents/AgentOperatorSummary";
import { OperationalAlertsPanel } from "@/components/agents/OperationalAlertsPanel";
import { AcceptedAnalysisQueuePanel } from "@/components/agents/AcceptedAnalysisQueuePanel";
import {
  buildLatestActiveFailureByAgent,
  isAgentEffectivelyRunning,
} from "@/components/agents/alertState";

export default function OverviewPage() {
  const recentFailureSince = useMemo(
    () => new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    [],
  );
  const { data, isLoading, error } = useQuery({
    queryKey: getOverviewSummaryQueryKey(),
    queryFn: fetchOverviewSummary,
    refetchInterval: 30_000,
  });
  const pauseStatesQuery = useQuery({
    queryKey: getAgentPauseStatesQueryKey(),
    queryFn: fetchAgentPauseStates,
    refetchInterval: 10_000,
  });
  const latestRunsQuery = useQuery({
    queryKey: getLatestAgentRunsQueryKey(),
    queryFn: fetchLatestAgentRuns,
    refetchInterval: 15_000,
  });
  const failureEventsQuery = useQuery({
    queryKey: getFailureEventsQueryKey({
      since: recentFailureSince,
      limit: 8,
    }),
    queryFn: () =>
      fetchFailureEvents({
        since: recentFailureSince,
        limit: 8,
      }),
    refetchInterval: 10_000,
  });
  const gatewayRuntimeQuery = useQuery({
    queryKey: ["gateway", "runtime"],
    queryFn: fetchGatewayRuntime,
    refetchInterval: 30_000,
  });

  if (error) {
    return (
      <>
        <div className="topbar">
          <span className="topbar-title">Overview</span>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
          <div className="card" style={{ background: 'var(--red-dim)', borderColor: 'var(--red)' }}>
            Failed to load overview
          </div>
        </div>
      </>
    );
  }

  const latestRunAgents = latestRunsQuery.data?.agents ?? [];
  const pauseStates = pauseStatesQuery.data ?? [];
  const runningAgentNames = new Set<string>(
    latestRunAgents
      .filter((entry) =>
        isAgentEffectivelyRunning(
          entry,
          pauseStates.find((state) => state.agent_name === entry.agent_name),
        ),
      )
      .map((entry) => entry.agent_name),
  );
  const runningAgents = runningAgentNames.size;
  const readyAgents =
    data?.agents.filter((agent) => !agent.is_paused && !runningAgentNames.has(agent.agent_name) && agent.status !== 'failed').length || 0;
  const healthyAgents = data?.agents.filter(a => !a.is_paused && a.status !== 'failed').length || 0;
  const reposDiscovered24h = data?.ingestion.discovered_last_24h || 0;
  const acceptedRepos = data?.triage.accepted || 0;
  const pausedAgents = data?.agents.filter((agent) => agent.is_paused).length || 0;
  const failedAgents = data?.agents.filter((agent) => !agent.is_paused && agent.status === "failed").length || 0;
  const openIncidents = pausedAgents + failedAgents;
  const historicalFailureEvents = data?.failures.total_failures || 0;
  const tokenBurn24h = data?.token_usage.total_tokens_24h || 0;
  const topTokenAgent = data?.agents.find(
    (agent) => agent.agent_name === data?.token_usage.top_consumer_agent_name,
  );
  const activeFailureByAgent = buildLatestActiveFailureByAgent(
    failureEventsQuery.data ?? [],
    latestRunAgents,
    pauseStates,
  );
  const agentsNeedingAttention = latestRunAgents.filter((entry) => {
    const paused = pauseStates.some((state) => state.agent_name === entry.agent_name && state.is_paused);
    const failure = activeFailureByAgent.has(entry.agent_name);
    return Boolean(paused || failure || entry.latest_run?.status === "failed");
  });

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Overview</span>
        <span className="topbar-breadcrumb">mission control</span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
        {isLoading ? (
          <div style={{ color: 'var(--text-3)' }}>Loading...</div>
        ) : data ? (
          <>
            <OperationalAlertsPanel
              pauseStates={pauseStatesQuery.data ?? []}
              failureEvents={failureEventsQuery.data ?? []}
              agents={data.agents}
              agentStatuses={latestRunsQuery.data?.agents ?? []}
            />
            <GitHubBudgetPanel snapshot={gatewayRuntimeQuery.data?.runtime.github_api_budget} />
            <GeminiKeyPoolPanel snapshot={gatewayRuntimeQuery.data?.runtime.gemini_api_key_pool} />

            <div className="hero-strip mb-16">
              <div>
                <h2>Mission Control</h2>
                <div className="sub">
                  {data?.agents.length || 0} agents · {runningAgents} running now · {readyAgents} ready
                </div>
              </div>
              <div className="flex items-center gap-12">
                <div className="mode-pill mode-active">
                  <span className="dot dot-green" style={{ width: '6px', height: '6px', borderRadius: '50%', display: 'inline-block' }}></span>
                  Auto-discovery ON
                </div>
                <button className="btn btn-primary">▶ Resume Firehose</button>
                <button className="btn">⌘ Command…</button>
              </div>
            </div>

            <div className="cmd-bar mb-16">
              <span className="cmd-icon">⌘</span>
              <span className="cmd-text">Standing order: watch for B2B workflow tools with rising star velocity and low hosted competition</span>
              <span className="cmd-meta">Updated 2m ago</span>
              <button className="btn btn-sm">Edit</button>
            </div>

            <div className="section-head">
              <span className="section-title">Who Needs Attention</span>
              <div className="section-line"></div>
            </div>
            <div className="grid g3 mb-16">
              {agentsNeedingAttention
                .slice(0, 3)
                .map((entry) => (
                  <AgentOperatorSummary
                    key={entry.agent_name}
                    entry={entry}
                    pauseState={pauseStates.find((state) => state.agent_name === entry.agent_name)}
                    failureEvent={activeFailureByAgent.get(entry.agent_name)}
                    title={entry.display_name}
                  />
                ))}
              {agentsNeedingAttention.length === 0 ? (
                <div className="card" style={{ gridColumn: "1 / -1" }}>
                  Nothing needs operator attention right now.
                </div>
              ) : null}
            </div>

            <div className="section-head">
              <span className="section-title">System Health</span>
              <div className="section-line"></div>
            </div>
            <div className="grid g5 mb-16">
              <div className="card metric-card">
                <div className="card-label">Healthy Agents</div>
                <div className="card-metric">{healthyAgents}<span style={{ fontSize: '16px', color: 'var(--text-2)' }}>/{data.agents.length}</span></div>
                <div className="flex items-center gap-8 mt-8">
                  <span className={`badge ${openIncidents > 0 ? "badge-yellow" : "badge-green"}`}>
                    ● {openIncidents > 0 ? "Attention" : "Stable"}
                  </span>
                </div>
                <div className="progress mt-8">
                  <div className="progress-bar progress-green" style={{ width: `${data.agents.length ? (healthyAgents / data.agents.length) * 100 : 0}%` }}></div>
                </div>
              </div>
              <div className="card metric-card">
                <div className="card-label">Open Incidents</div>
                <div className="card-metric">{openIncidents}</div>
                <div className="flex items-center gap-8 mt-8">
                  {pausedAgents > 0 && <span className="badge badge-red">{pausedAgents} Paused agents</span>}
                  {failedAgents > 0 && <span className="badge badge-yellow">{failedAgents} Failed agents</span>}
                  {openIncidents === 0 && <span className="badge badge-green">No active incidents</span>}
                </div>
                <div className="card-sub">{historicalFailureEvents} historical failure events recorded</div>
              </div>
              <div className="card metric-card">
                <div className="card-label">Repos Discovered (24h)</div>
                <div className="card-metric">{reposDiscovered24h}</div>
                <div className="card-sub">
                  {data.ingestion.firehose_discovered_last_24h} firehose · {data.ingestion.backfill_discovered_last_24h} backfill
                </div>
                <div className="card-sub">{data.analysis.completed} analyzed · {data.triage.accepted} accepted</div>
              </div>
              <div className="card metric-card">
                <div className="card-label">Token Burn (24h)</div>
                <div className="card-metric">{formatTokenCount(tokenBurn24h)}</div>
                <div className="flex items-center gap-8 mt-8">
                  <span className={`badge ${tokenBurn24h > 0 ? "badge-yellow" : "badge-muted"}`}>
                    {tokenBurn24h > 0 ? "Tracked" : "No LLM usage"}
                  </span>
                </div>
                <div className="card-sub">
                  {tokenBurn24h > 0 && topTokenAgent
                    ? `${topTokenAgent.display_name} used ${formatTokenCount(data.token_usage.top_consumer_tokens_24h)} in the last 24h`
                    : "No model-backed runs recorded in the last 24h"}
                </div>
              </div>
              <div className="card metric-card">
                <div className="card-label">Accepted Repos</div>
                <div className="card-metric">{acceptedRepos}</div>
                <div className="card-sub">{data.triage.rejected} rejected · {data.triage.pending} pending</div>
                <div className="card-sub">Accepted through triage, not synthesized business ideas.</div>
              </div>
            </div>

            <div className="section-head">
              <span className="section-title">Pipeline Flow</span>
              <div className="section-line"></div>
            </div>
            <div className="card mb-16">
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', overflowX: 'auto' }}>
                <PipelineNode name="Firehose" count={data.backlog.queue_pending} status="in queue" active={data.ingestion.firehose_discovered_last_24h > 0} />
                <div style={{ color: 'var(--text-3)', fontSize: '20px' }}>→</div>
                <PipelineNode name="Backfill" count={0} status="historical" active={false} />
                <div style={{ color: 'var(--text-3)', fontSize: '20px' }}>→</div>
                <PipelineNode name="Bouncer" count={data.triage.pending} status="triage" active={data.triage.pending > 0} />
                <div style={{ color: 'var(--text-3)', fontSize: '20px' }}>→</div>
                <PipelineNode name="Analyst" count={data.analysis.in_progress} status="analyzing" active={data.analysis.in_progress > 0} />
                <div style={{ color: 'var(--text-3)', fontSize: '20px' }}>→</div>
                <PipelineNode name="Combiner" count={0} status="synthesis" active={false} />
                <div style={{ color: 'var(--text-3)', fontSize: '20px' }}>→</div>
                <PipelineNode name="Ideas DB" count={acceptedRepos} status="accepted" active={acceptedRepos > 0} />
              </div>
            </div>

            <div className="mb-16">
              <AcceptedAnalysisQueuePanel
                pendingCount={data.analysis.pending}
                title="Accepted Repos Waiting For Analyst"
              />
            </div>

            <div className="section-head">
              <span className="section-title">Operator Control</span>
              <div className="section-line"></div>
            </div>
            <div className="grid g-wide mb-16">
              <div className="ctrl-dock">
                <div className="ctrl-dock-head">
                  <span className="card-title">Active Control Dock</span>
                  <span className="badge badge-green">Ready</span>
                </div>
                <div className="ctrl-dock-body">
                  <div className="ctrl-row"><span className="ctrl-label">Target</span><span className="ctrl-value">Firehose Agent</span></div>
                  <div className="ctrl-row"><span className="ctrl-label">Action</span><span className="ctrl-value">Resume after safe pause</span></div>
                  <div className="ctrl-row"><span className="ctrl-label">Scope</span><span className="ctrl-value">Remaining batch only</span></div>
                  <div className="mt-12 flex gap-8">
                    <button className="btn btn-primary">Execute: Resume Firehose</button>
                    <button className="btn btn-danger">Cancel</button>
                  </div>
                </div>
              </div>
              <div className="ctrl-dock">
                <div className="ctrl-dock-head">
                  <span className="card-title">Pending Commands</span>
                  <span className="badge badge-muted">0</span>
                </div>
                <div className="ctrl-dock-body">
                  <div style={{ fontSize: '12px', color: 'var(--text-3)', textAlign: 'center', padding: '20px' }}>No pending commands</div>
                </div>
              </div>
            </div>

            <div className="section-head">
              <span className="section-title">Agent Status</span>
              <div className="section-line"></div>
            </div>
            <div className="grid g3 mb-16">
              <div className="card">
                <div className="card-header"><span className="card-title">Agent Matrix</span></div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {data.agents.map((agent) => {
                      const latestEntry = latestRunAgents.find((entry) => entry.agent_name === agent.agent_name);
                      const pauseState = pauseStates.find((state) => state.agent_name === agent.agent_name);
                      const badgeTone = agent.is_paused
                        ? "red"
                        : isAgentEffectivelyRunning(latestEntry, pauseState)
                          ? "yellow"
                          : "green";
                      return (
                    <div key={agent.agent_name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-0)' }}>{agent.agent_name}</span>
                      <span className={`badge badge-${badgeTone}`}>●</span>
                    </div>
                      );
                    })}
                </div>
              </div>
              <div className="card">
                <div className="card-header"><span className="card-title">Recent Activity</span></div>
                <div style={{ fontSize: '12px', color: 'var(--text-2)' }}>
                  <div style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>Analyst completed batch #47</div>
                  <div style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>Firehose discovered 23 repos</div>
                  <div style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>Bouncer filtered 12 repos</div>
                  <div style={{ padding: '8px 0' }}>Overlord health check passed</div>
                </div>
              </div>
              <div className="card">
                <div className="card-header"><span className="card-title">Opportunities Now</span></div>
                <div style={{ fontSize: '12px', color: 'var(--text-2)' }}>
                  <div style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                    <div style={{ color: 'var(--text-0)', marginBottom: '4px' }}>High-fit repos ready</div>
                    <div>{data.triage.accepted} repos awaiting review</div>
                  </div>
                  <div style={{ padding: '8px 0' }}>
                    <div style={{ color: 'var(--text-0)', marginBottom: '4px' }}>Analysis capacity</div>
                    <div>Can process {data.analysis.pending} more repos</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="section-head">
              <span className="section-title">Agent Functions</span>
              <div className="section-line"></div>
            </div>
            <div className="grid g3">
              {data.agents.map((agent) => (
                <AgentDescription
                  key={agent.agent_name}
                  name={agent.display_name}
                  desc={agent.description}
                  role={agent.role_label}
                  usesAI={agent.uses_model}
                  model={agent.configured_model}
                  provider={agent.configured_provider}
                  githubBacked={agent.uses_github_token}
                />
              ))}
            </div>

            <div className="section-head">
              <span className="section-title">Trends & Schedule</span>
              <div className="section-line"></div>
            </div>
            <div className="grid g3 mb-16">
              <div className="card">
                <div className="card-header"><span className="card-title">Trend Watch</span></div>
                <div style={{ fontSize: '12px', color: 'var(--text-2)' }}>
                  <div style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                    <div style={{ color: 'var(--text-0)' }}>Repo intake velocity</div>
                    <div className="delta delta-up">↑ 34% vs yesterday</div>
                  </div>
                  <div style={{ padding: '8px 0' }}>
                    <div style={{ color: 'var(--text-0)' }}>Token consumption</div>
                    <div className="delta delta-up">↑ 12% trending up</div>
                  </div>
                </div>
              </div>
              <div className="card">
                <div className="card-header"><span className="card-title">Scheduled Events</span></div>
                <div style={{ fontSize: '12px', color: 'var(--text-2)' }}>
                  <div style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>Backfill run in 2h</div>
                  <div style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>Weekly combiner in 6h</div>
                  <div style={{ padding: '8px 0' }}>Maintenance window tomorrow</div>
                </div>
              </div>
              <div className="card">
                <div className="card-header"><span className="card-title">Backlog Pressure</span></div>
                <div style={{ fontSize: '12px', color: 'var(--text-2)' }}>
                  <div style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                    <div style={{ color: 'var(--text-0)' }}>Queue depth</div>
                    <div>{data.backlog.queue_pending} pending</div>
                  </div>
                  <div style={{ padding: '8px 0' }}>
                    <div style={{ color: 'var(--text-0)' }}>Processing rate</div>
                    <div>~{data.analysis.completed}/day</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="grid g-wide">
              <div className="card">
                <div className="card-header"><span className="card-title">Interest Areas</span></div>
                <div style={{ fontSize: '12px', color: 'var(--text-2)', lineHeight: '1.6' }}>
                  Watching B2B workflow tools, developer productivity, and AI-assisted coding platforms. Focus on repos with rising star velocity and low hosted competition.
                </div>
              </div>
              <div className="card">
                <div className="card-header"><span className="card-title">Recovery Notes</span></div>
                <div style={{ fontSize: '12px', color: 'var(--text-2)' }}>No active recovery procedures</div>
              </div>
            </div>
          </>
        ) : null}
      </div>
    </>
  );
}

function PipelineNode({ name, count, status, active }: { name: string; count: number; status: string; active: boolean }) {
  return (
    <div style={{
      background: active ? 'var(--bg-3)' : 'var(--bg-2)',
      border: `1px solid ${active ? 'var(--border-h)' : 'var(--border)'}`,
      borderRadius: '8px',
      padding: '12px 16px',
      minWidth: '120px',
      textAlign: 'center'
    }}>
      <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-0)', marginBottom: '4px' }}>{name}</div>
      <div style={{ fontSize: '24px', fontWeight: 700, color: active ? 'var(--amber)' : 'var(--text-2)', fontFamily: 'var(--mono)' }}>{count}</div>
      <div style={{ fontSize: '10px', color: 'var(--text-3)', marginTop: '4px' }}>{status}</div>
    </div>
  );
}

function AgentDescription({
  name,
  desc,
  role,
  usesAI,
  model,
  provider,
  githubBacked,
}: {
  name: string;
  desc: string;
  role: string;
  usesAI: boolean;
  model?: string | null;
  provider?: string | null;
  githubBacked: boolean;
}) {
  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-0)' }}>{name}</span>
        {usesAI && <span className="badge badge-blue">AI</span>}
        {githubBacked && <span className="badge badge-muted">GitHub API</span>}
      </div>
      <div style={{ fontSize: '11px', color: 'var(--text-3)', marginBottom: '8px', fontFamily: 'var(--mono)' }}>{role}</div>
      <div style={{ fontSize: '12px', color: 'var(--text-2)', lineHeight: '1.5' }}>{desc}</div>
      <div style={{ fontSize: '11px', color: 'var(--text-3)', marginTop: '8px', fontFamily: 'var(--mono)' }}>
        Provider: {provider ?? "local-only"}
      </div>
      <div style={{ fontSize: '11px', color: 'var(--text-3)', marginTop: '4px', fontFamily: 'var(--mono)' }}>
        Model: {model ?? "none"}
      </div>
    </div>
  );
}

function formatTokenCount(value: number) {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return `${value}`;
}

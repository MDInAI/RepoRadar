"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchIncidents, getIncidentsQueryKey, type Incident } from "@/api/incidents";
import { fetchOverviewSummary, getOverviewSummaryQueryKey } from "@/api/overview";

export default function IncidentsClient() {
  const [selected, setSelected] = useState<Incident | null>(null);

  const { data } = useQuery({
    queryKey: getIncidentsQueryKey({ limit: 50 }),
    queryFn: () => fetchIncidents({ limit: 50 }),
    refetchInterval: 30000,
  });
  const overviewQuery = useQuery({
    queryKey: getOverviewSummaryQueryKey(),
    queryFn: fetchOverviewSummary,
    refetchInterval: 30000,
  });

  const incidents = data ?? [];
  const pausedAgents = overviewQuery.data?.agents.filter((agent) => agent.is_paused).length ?? 0;
  const failedAgents =
    overviewQuery.data?.agents.filter((agent) => !agent.is_paused && agent.status === "failed").length ?? 0;
  const activeWarnings = 0;
  const recentCriticalEvents = incidents.filter((i) => i.severity === "critical").length;
  const recentErrorEvents = incidents.filter((i) => i.severity === "error").length;
  const recentWarningEvents = incidents.filter((i) => i.severity === "warning").length;

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Incidents</span>
        <span className="topbar-breadcrumb">monitoring</span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '20px' }}>
        <div className="grid g3 mb-16">
          <SeverityCard
            label="Active Critical"
            count={pausedAgents}
            color="var(--red)"
            desc="Agents currently paused and needing operator attention"
          />
          <SeverityCard
            label="Active Error"
            count={failedAgents}
            color="var(--yellow)"
            desc="Agents whose latest run failed and are not currently paused"
          />
          <SeverityCard
            label="Active Warning"
            count={activeWarnings}
            color="var(--blue)"
            desc="Current warning-level active incidents are not yet tracked separately"
          />
        </div>

        <div className="card mb-16">
          <div className="card-label" style={{ marginBottom: "8px" }}>Recent Incident Events</div>
          <div style={{ fontSize: "12px", color: "var(--text-2)", lineHeight: 1.6 }}>
            This list is a historical event stream, not a deduplicated list of currently open incidents.
          </div>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "12px" }}>
            <span className="badge badge-red">{recentCriticalEvents} Critical events</span>
            <span className="badge badge-yellow">{recentErrorEvents} Error events</span>
            <span className="badge badge-blue">{recentWarningEvents} Warning events</span>
            <span className="badge badge-muted">{incidents.length} Rows shown</span>
          </div>
        </div>

        <div style={{
          background: 'var(--bg-2)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden'
        }}>
          {incidents.length === 0 ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-3)' }}>
              No incidents recorded
            </div>
          ) : (
            incidents.map((inc) => (
              <div key={inc.id} onClick={() => setSelected(inc)} style={{
                padding: '16px 20px',
                borderBottom: '1px solid var(--border)',
                cursor: 'pointer',
                transition: 'background 0.15s'
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-3)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <SeverityBadge severity={inc.severity} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '13px', color: 'var(--text-0)', fontWeight: 500 }}>
                      {inc.event_type}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-3)', marginTop: '2px' }}>
                      {inc.agent_name} · {new Date(inc.created_at).toLocaleString()}
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {selected && (
          <div style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000
          }} onClick={() => setSelected(null)}>
            <div style={{
              background: 'var(--bg-2)',
              border: '1px solid var(--border)',
              borderRadius: '10px',
              padding: '24px',
              maxWidth: '600px',
              width: '90%'
            }} onClick={(e) => e.stopPropagation()}>
              <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>
                Incident Details
              </h3>
              <div style={{ fontSize: '13px', color: 'var(--text-2)', lineHeight: 1.6 }}>
                <div><strong>Type:</strong> {selected.event_type}</div>
                <div><strong>Agent:</strong> {selected.agent_name}</div>
                <div><strong>Severity:</strong> {selected.severity}</div>
                <div><strong>Time:</strong> {new Date(selected.created_at).toLocaleString()}</div>
                {selected.message && <div style={{ marginTop: '12px' }}>{selected.message}</div>}
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function SeverityCard({
  label,
  count,
  color,
  desc,
}: {
  label: string;
  count: number;
  color: string;
  desc: string;
}) {
  return (
    <div className="card">
      <div className="card-label" style={{ marginBottom: '8px' }}>{label}</div>
      <div className="card-metric" style={{ color, marginBottom: '8px' }}>{count}</div>
      <div style={{ fontSize: '11px', color: 'var(--text-3)' }}>{desc}</div>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: Incident["severity"] }) {
  const colors = {
    critical: 'var(--red)',
    error: 'var(--yellow)',
    warning: 'var(--blue)',
  };
  return (
    <div style={{
      width: '8px',
      height: '8px',
      borderRadius: '50%',
      background: colors[severity as keyof typeof colors]
    }} />
  );
}

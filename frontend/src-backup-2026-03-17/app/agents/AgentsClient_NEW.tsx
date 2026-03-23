"use client";

export default function AgentsClient() {
  const agents = [
    { name: "Overlord", icon: "👑", status: "running", desc: "Orchestration coordinator" },
    { name: "Firehose", icon: "🔥", status: "running", desc: "Real-time discovery" },
    { name: "Backfill", icon: "⏮️", status: "running", desc: "Historical processing" },
    { name: "Bouncer", icon: "🚪", status: "running", desc: "Repository filtering" },
    { name: "Analyst", icon: "🔬", status: "running", desc: "Content analysis" },
  ];

  return (
    <div style={{ background: 'var(--bg-0)', minHeight: '100vh' }}>
      <div style={{
        height: '44px',
        background: 'var(--bg-1)',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px'
      }}>
        <span style={{ fontWeight: 600, fontSize: '14px' }}>Agents</span>
      </div>

      <div style={{ padding: '24px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px' }}>
          {agents.map((agent) => (
            <div key={agent.name} style={{
              background: 'var(--bg-2)',
              border: '1px solid var(--border)',
              borderRadius: '10px',
              padding: '20px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                <span style={{ fontSize: '32px' }}>{agent.icon}</span>
                <div>
                  <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-0)' }}>{agent.name}</h3>
                  <p style={{ fontSize: '12px', color: 'var(--text-3)' }}>{agent.desc}</p>
                </div>
              </div>
              <div style={{
                display: 'inline-block',
                padding: '4px 12px',
                background: 'var(--green-dim)',
                color: 'var(--green)',
                borderRadius: '6px',
                fontSize: '11px',
                fontWeight: 600,
                textTransform: 'uppercase'
              }}>
                {agent.status}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

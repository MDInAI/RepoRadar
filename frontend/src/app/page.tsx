"use client";

import Link from "next/link";

export default function Home() {
  return (
    <div style={{ background: 'var(--bg-0)', minHeight: '100vh', padding: '40px' }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
        <header style={{ marginBottom: '48px' }}>
          <h1 style={{ fontSize: '32px', fontWeight: 700, color: 'var(--text-0)', marginBottom: '8px' }}>
            Agentic-Workflow
          </h1>
          <p style={{ color: 'var(--text-2)', fontSize: '14px' }}>
            Multi-agent repository discovery and analysis system
          </p>
        </header>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
          <NavCard href="/overview" title="Overview" desc="System metrics and agent status" />
          <NavCard href="/live" title="Live Ops" desc="Real-time command surface for all agents" />
          <NavCard href="/control" title="Control Panel" desc="Advanced agent configuration" />
          <NavCard href="/agents" title="Agents" desc="Monitor runtime agents" />
          <NavCard href="/repositories" title="Repositories" desc="Browse discovered repos" />
          <NavCard href="/ideas" title="Ideas" desc="Synthesized insights" />
          <NavCard href="/incidents" title="Incidents" desc="System events and alerts" />
          <NavCard href="/settings" title="Settings" desc="Configuration and validation" />
        </div>
      </div>
    </div>
  );
}

function NavCard({ href, title, desc }: { href: string; title: string; desc: string }) {
  return (
    <Link href={href} style={{
      display: 'block',
      padding: '24px',
      background: 'var(--bg-2)',
      border: '1px solid var(--border)',
      borderRadius: '10px',
      textDecoration: 'none',
      transition: 'all 0.2s'
    }}
    onMouseEnter={(e) => {
      e.currentTarget.style.background = 'var(--bg-3)';
      e.currentTarget.style.borderColor = 'var(--border-h)';
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.background = 'var(--bg-2)';
      e.currentTarget.style.borderColor = 'var(--border)';
    }}>
      <h2 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-0)', marginBottom: '8px' }}>
        {title}
      </h2>
      <p style={{ fontSize: '13px', color: 'var(--text-2)' }}>
        {desc}
      </p>
    </Link>
  );
}

"use client";

import Link from "next/link";

export default function Home() {
  return (
    <div style={{ background: 'var(--bg-0)', minHeight: '100vh', padding: '40px' }}>
      <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
        <header style={{ marginBottom: '48px' }}>
          <h1 style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-0)', marginBottom: '8px' }}>
            Agentic-Workflow
          </h1>
          <p style={{ color: 'var(--text-2)', fontSize: '14px' }}>
            Multi-agent repository discovery and analysis system
          </p>
        </header>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
          <NavCard href="/overview" title="Dashboard" desc="Live monitoring, pipeline status, agent health, and system metrics — all in one place." primary />
          <NavCard href="/control" title="Control Panel" desc="Run, pause, resume agents. Configure settings, manage resources." />
          <NavCard href="/repositories" title="Repositories" desc="Browse and filter discovered repos. Star, tag, and review candidates." />
          <NavCard href="/ideas" title="Ideas" desc="Synthesized insights, family workspace, and combiner results." />
          <NavCard href="/incidents" title="Incidents" desc="System events, failure alerts, and historical event log." />
          <NavCard href="/settings" title="Settings" desc="System configuration and validation." />
        </div>
      </div>
    </div>
  );
}

function NavCard({ href, title, desc, primary }: { href: string; title: string; desc: string; primary?: boolean }) {
  return (
    <Link href={href} style={{
      display: 'block',
      padding: '24px',
      background: primary ? 'color-mix(in srgb, var(--amber-dim) 40%, var(--bg-2))' : 'var(--bg-2)',
      border: `1px solid ${primary ? 'rgba(212, 162, 58, 0.25)' : 'var(--border)'}`,
      borderRadius: '10px',
      textDecoration: 'none',
      transition: 'all 0.2s',
      borderLeft: primary ? '3px solid var(--amber)' : undefined,
    }}
    onMouseEnter={(e) => {
      e.currentTarget.style.background = primary ? 'color-mix(in srgb, var(--amber-dim) 55%, var(--bg-2))' : 'var(--bg-3)';
      e.currentTarget.style.borderColor = primary ? 'rgba(212, 162, 58, 0.4)' : 'var(--border-h)';
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.background = primary ? 'color-mix(in srgb, var(--amber-dim) 40%, var(--bg-2))' : 'var(--bg-2)';
      e.currentTarget.style.borderColor = primary ? 'rgba(212, 162, 58, 0.25)' : 'var(--border)';
    }}>
      <h2 style={{ fontSize: '16px', fontWeight: 600, color: primary ? 'var(--amber)' : 'var(--text-0)', marginBottom: '8px' }}>
        {title}
      </h2>
      <p style={{ fontSize: '13px', color: 'var(--text-2)', lineHeight: 1.5 }}>
        {desc}
      </p>
    </Link>
  );
}

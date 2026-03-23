"use client";

export function RepositoriesCatalogClient() {
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
        <span style={{ fontWeight: 600, fontSize: '14px' }}>Repositories</span>
      </div>

      <div style={{ padding: '24px' }}>
        <div style={{
          background: 'var(--bg-2)',
          border: '1px solid var(--border)',
          borderRadius: '10px',
          padding: '60px 40px',
          textAlign: 'center'
        }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>📦</div>
          <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-0)', marginBottom: '8px' }}>
            No Repositories Yet
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--text-3)', marginBottom: '20px' }}>
            Repositories will appear here as Firehose and Backfill discover them from GitHub
          </p>
          <a href="/control" style={{
            display: 'inline-block',
            padding: '10px 20px',
            background: 'var(--amber)',
            color: '#0d0f12',
            borderRadius: '6px',
            textDecoration: 'none',
            fontSize: '13px',
            fontWeight: 600
          }}>
            Configure Agents
          </a>
        </div>
      </div>
    </div>
  );
}

"use client";

export default function SettingsPage() {
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
        <span style={{ fontWeight: 600, fontSize: '14px' }}>Settings</span>
      </div>

      <div style={{ padding: '24px', maxWidth: '800px' }}>
        <div style={{
          background: 'var(--bg-2)',
          border: '1px solid var(--border)',
          borderRadius: '10px',
          padding: '20px',
          marginBottom: '16px'
        }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '16px', color: 'var(--text-0)' }}>
            System Status
          </h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--green)' }} />
            <span style={{ fontSize: '13px', color: 'var(--text-2)' }}>All systems operational</span>
          </div>
        </div>

        <div style={{
          background: 'var(--bg-2)',
          border: '1px solid var(--border)',
          borderRadius: '10px',
          padding: '20px'
        }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '16px', color: 'var(--text-0)' }}>
            Configuration
          </h3>
          <div style={{ fontSize: '13px', color: 'var(--text-2)', lineHeight: 1.6 }}>
            <div style={{ marginBottom: '12px' }}>
              <strong style={{ color: 'var(--text-1)' }}>Gateway:</strong> ws://127.0.0.1:18789
            </div>
            <div style={{ marginBottom: '12px' }}>
              <strong style={{ color: 'var(--text-1)' }}>Workspace:</strong> /Users/bot/.openclaw/workspace
            </div>
            <div>
              <strong style={{ color: 'var(--text-1)' }}>Runtime Mode:</strong> Multi-agent
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

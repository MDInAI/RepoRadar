"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function IconRail() {
  const pathname = usePathname();

  const links = [
    { href: "/overview", icon: "📊", label: "Overview" },
    { href: "/live", icon: "🛰️", label: "Live Ops" },
    { href: "/control", icon: "🎛️", label: "Control" },
    { href: "/agents", icon: "🤖", label: "Agents" },
    { href: "/repositories", icon: "📦", label: "Repos" },
    { href: "/ideas", icon: "💡", label: "Ideas" },
    { href: "/incidents", icon: "⚠️", label: "Incidents" },
    { href: "/settings", icon: "⚙️", label: "Settings" },
  ];

  return (
    <div style={{
      width: '56px',
      background: 'var(--bg-1)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      padding: '12px 0',
      gap: '4px',
      height: '100vh',
      zIndex: 100
    }}>
      <Link href="/overview" style={{
        width: '36px',
        height: '36px',
        borderRadius: '8px',
        background: 'linear-gradient(135deg, var(--amber), #8a6a1a)',
        display: 'grid',
        placeItems: 'center',
        fontFamily: 'var(--mono)',
        fontWeight: 700,
        fontSize: '13px',
        color: '#0d0f12',
        marginBottom: '12px',
        textDecoration: 'none'
      }}>
        AW
      </Link>

      {links.map((link) => {
        const isActive = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            title={link.label}
            style={{
              width: '40px',
              height: '40px',
              borderRadius: '6px',
              display: 'grid',
              placeItems: 'center',
              cursor: 'pointer',
              color: isActive ? 'var(--amber)' : 'var(--text-3)',
              background: isActive ? 'var(--amber-dim)' : 'transparent',
              transition: 'all 0.15s',
              position: 'relative',
              textDecoration: 'none',
              fontSize: '18px'
            }}
          >
            {isActive && <div style={{
              position: 'absolute',
              left: '-1px',
              top: '10px',
              bottom: '10px',
              width: '2px',
              background: 'var(--amber)',
              borderRadius: '1px'
            }} />}
            {link.icon}
          </Link>
        );
      })}
    </div>
  );
}

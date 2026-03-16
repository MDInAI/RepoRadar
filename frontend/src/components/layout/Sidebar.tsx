"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function Sidebar() {
  const pathname = usePathname();

  const links = [
    { href: "/", label: "Home", icon: "🏠" },
    { href: "/overview", label: "Overview", icon: "📊" },
    { href: "/live", label: "Live Ops", icon: "🛰️" },
    { href: "/control", label: "Control Panel", icon: "🎛️" },
    { href: "/agents", label: "Agents", icon: "🤖" },
    { href: "/repositories", label: "Repositories", icon: "📦" },
    { href: "/ideas", label: "Ideas", icon: "💡" },
    { href: "/incidents", label: "Incidents", icon: "⚠️" },
    { href: "/settings", label: "Settings", icon: "⚙️" },
  ];

  return (
    <aside className="fixed left-0 top-0 h-screen w-64 bg-neutral-900 border-r border-neutral-800 flex flex-col">
      <div className="p-6 border-b border-neutral-800">
        <h1 className="text-xl font-bold text-indigo-400">Agentic Workflow</h1>
        <p className="text-xs text-neutral-500 mt-1">Multi-Agent Control</p>
      </div>

      <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
        {links.map((link) => {
          const isActive = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`
                flex items-center gap-3 px-4 py-3 rounded-lg transition-colors
                ${isActive
                  ? "bg-indigo-600 text-white"
                  : "text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
                }
              `}
            >
              <span className="text-xl">{link.icon}</span>
              <span className="font-medium">{link.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-neutral-800 text-xs text-neutral-500">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
          <span>System Online</span>
        </div>
      </div>
    </aside>
  );
}

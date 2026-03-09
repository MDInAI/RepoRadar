import Link from "next/link";

export default function Home() {
  return (
    <main className="flex flex-col min-h-screen p-8 max-w-5xl mx-auto">
      <header className="mb-12 border-b border-neutral-800 pb-8">
        <h1 className="text-3xl font-bold tracking-tight mb-2">Agentic-Workflow Dashboard</h1>
        <p className="text-neutral-400">
          Local-first intelligent repository discovery and idea synthesis.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <NavigationCard
          href="/overview"
          title="Overview"
          description="System metrics, queue progress, and live agent status."
        />
        <NavigationCard
          href="/repositories"
          title="Repositories"
          description="Browse, filter, and sort ingested repositories."
        />
        <NavigationCard
          href="/ideas"
          title="Ideas Workspace"
          description="Curate ideas and interact with combinations."
        />
        <NavigationCard
          href="/agents"
          title="Agents"
          description="Monitor and control active runtime agents."
        />
        <NavigationCard
          href="/incidents"
          title="Incidents"
          description="Review operational failures, rate limits, and system paused state."
        />
        <NavigationCard
          href="/settings"
          title="Settings & Configuration"
          description="Manage API keys, paths, and platform connections."
        />
      </div>
    </main>
  );
}

function NavigationCard({ href, title, description }: { href: string; title: string; description: string }) {
  return (
    <Link
      href={href}
      className="block p-6 rounded-xl border border-neutral-800 bg-neutral-900/50 hover:bg-neutral-800 hover:border-neutral-700 transition-colors shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
    >
      <h2 className="text-xl font-semibold mb-2 flex items-center justify-between">
        {title}
        <span className="text-indigo-400 text-sm">→</span>
      </h2>
      <p className="text-neutral-400 text-sm">
        {description}
      </p>
    </Link>
  );
}

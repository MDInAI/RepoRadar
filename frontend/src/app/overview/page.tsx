export default function OverviewPage() {
  return (
    <main className="p-8">
      <h1 className="text-2xl font-bold">Overview</h1>
      <p className="text-neutral-400">
        Placeholder for the operator overview. Future readiness cards will read
        the backend Gateway contract at <code>/api/v1/gateway/*</code>, where
        runtime mode is explicitly multi-agent and named-agent summaries stay
        backend-owned instead of coming directly from the browser to Gateway.
      </p>
    </main>
  );
}

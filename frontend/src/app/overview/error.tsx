"use client";

export default function OverviewError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#fff7ed_0%,#f8fafc_40%,#eef2ff_100%)] px-6 py-10 text-slate-900">
      <div className="mx-auto max-w-5xl">
        <h1 className="text-3xl font-semibold">Overview</h1>
        <p className="mt-4 max-w-2xl text-sm text-slate-600">
          The operator overview hit an unexpected client-side error.
        </p>
        <div className="mt-8 rounded-3xl border border-red-200 bg-white/90 p-6 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-red-700">
            Runtime Error
          </p>
          <p className="mt-3 text-sm text-slate-700">
            {error.message || "The overview could not recover automatically."}
          </p>
          <button
            className="mt-5 rounded-full bg-slate-950 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-white"
            onClick={reset}
            type="button"
          >
            Retry overview
          </button>
        </div>
      </div>
    </main>
  );
}

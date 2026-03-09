import { Suspense } from "react";

import { RepositoriesCatalogClient } from "./RepositoriesCatalogClient";

function RepositoryCatalogFallback() {
  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#fff8f1_0%,#f8fafc_40%,#dbeafe_100%)] px-6 py-10 text-slate-900">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <section className="rounded-[2rem] border border-black/10 bg-white/90 px-6 py-16 text-center shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)]">
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">
            Loading
          </p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-950">
            Preparing repository catalog
          </h1>
          <p className="mt-3 text-sm text-slate-600">
            Hydrating the URL-driven repository corpus grid.
          </p>
        </section>
      </div>
    </main>
  );
}

export default function RepositoriesPage() {
  return (
    <Suspense fallback={<RepositoryCatalogFallback />}>
      <RepositoriesCatalogClient />
    </Suspense>
  );
}

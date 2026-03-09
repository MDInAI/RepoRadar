"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { startTransition } from "react";

import {
  buildRepositoryCatalogSearchParams,
  clearAllRepositoryCatalogFilters,
  clearRepositoryCatalogFilter,
  describeRepositoryCatalogFilters,
  fetchRepositoryCatalog,
  getRepositoryCatalogValidationMessage,
  getRepositoryCatalogQueryKey,
  parseRepositoryCatalogSearchParams,
  type RepositoryAnalysisStatus,
  type RepositoryCatalogSortBy,
  type RepositoryCatalogSortOrder,
  type RepositoryDiscoverySource,
  type RepositoryMonetizationPotential,
  type RepositoryTriageStatus,
} from "@/api/repositories";
import { CatalogFilterBar } from "@/components/repositories/CatalogFilterBar";
import { CatalogPagination } from "@/components/repositories/CatalogPagination";
import { RepositoryCatalogTable } from "@/components/repositories/RepositoryCatalogTable";

function buildRepositoriesUrl(search: string): string {
  return search.length > 0 ? `/repositories?${search}` : "/repositories";
}

export function RepositoriesCatalogClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const viewState = parseRepositoryCatalogSearchParams(searchParams);
  const activeFilterChips = describeRepositoryCatalogFilters(viewState);
  const validationMessage = getRepositoryCatalogValidationMessage(viewState);

  const catalogQuery = useQuery({
    queryKey: getRepositoryCatalogQueryKey(viewState),
    queryFn: () => fetchRepositoryCatalog(viewState),
    placeholderData: keepPreviousData,
    enabled: validationMessage === null,
  });

  const updateViewState = (
    patch: Partial<typeof viewState>,
    options?: { resetPage?: boolean },
  ) => {
    const nextState = {
      ...viewState,
      ...patch,
      page: options?.resetPage === false ? patch.page ?? viewState.page : patch.page ?? 1,
    };
    const nextSearch = buildRepositoryCatalogSearchParams(nextState).toString();
    startTransition(() => {
      router.replace(buildRepositoriesUrl(nextSearch), { scroll: false });
    });
  };

  const handleSearchChange = (search: string) => {
    updateViewState({ search: search.trim().length > 0 ? search : null });
  };

  const handleSourceChange = (source: RepositoryDiscoverySource | null) => {
    updateViewState({ source });
  };

  const handleTriageStatusChange = (triageStatus: RepositoryTriageStatus | null) => {
    updateViewState({ triageStatus });
  };

  const handleAnalysisStatusChange = (analysisStatus: RepositoryAnalysisStatus | null) => {
    updateViewState({ analysisStatus });
  };

  const handleMonetizationChange = (
    monetization: RepositoryMonetizationPotential | null,
  ) => {
    updateViewState({ monetization });
  };

  const handleMinStarsChange = (minStars: number | null) => {
    updateViewState({ minStars: Number.isNaN(minStars) ? null : minStars });
  };

  const handleMaxStarsChange = (maxStars: number | null) => {
    updateViewState({ maxStars: Number.isNaN(maxStars) ? null : maxStars });
  };

  const handleSortChange = (sort: RepositoryCatalogSortBy) => {
    updateViewState({ sort });
  };

  const handleOrderChange = (order: RepositoryCatalogSortOrder) => {
    updateViewState({ order }, { resetPage: false });
  };

  const handlePageChange = (page: number) => {
    updateViewState({ page }, { resetPage: false });
  };

  const handlePageSizeChange = (pageSize: number) => {
    updateViewState({ pageSize });
  };

  const handleRemoveChip = (key: (typeof activeFilterChips)[number]["key"]) => {
    const nextState = clearRepositoryCatalogFilter(viewState, key);
    const nextSearch = buildRepositoryCatalogSearchParams(nextState).toString();
    startTransition(() => {
      router.replace(buildRepositoriesUrl(nextSearch), { scroll: false });
    });
  };

  const handleClearAll = () => {
    const nextSearch = buildRepositoryCatalogSearchParams(
      clearAllRepositoryCatalogFilters(viewState),
    ).toString();
    startTransition(() => {
      router.replace(buildRepositoriesUrl(nextSearch), { scroll: false });
    });
  };

  const data = validationMessage === null ? catalogQuery.data : undefined;
  const errorMessage =
    catalogQuery.error instanceof Error
      ? catalogQuery.error.message
      : "Unable to load repository catalog.";

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#fff8f1_0%,#f8fafc_40%,#dbeafe_100%)] px-6 py-10 text-slate-900">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <header className="rounded-[2.2rem] border border-black/10 bg-white/80 px-6 py-7 shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)] backdrop-blur">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.32em] text-orange-700">
                Repository Corpus Grid
              </p>
              <h1 className="mt-3 text-4xl font-semibold tracking-tight text-slate-950">
                Browse analyzed repositories
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-600">
                Filter by source, triage, analysis state, fit score, and popularity without
                pulling the full dataset into the browser. Each row routes to the repository
                dossier surface.
              </p>
            </div>

            <div className="rounded-[1.6rem] border border-orange-200 bg-orange-50/90 px-4 py-4 text-sm text-orange-950">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-orange-700">
                Sort State
              </p>
              <p className="mt-2 font-semibold">
                {viewState.sort.replace("_", " ")} / {viewState.order}
              </p>
            </div>
          </div>
        </header>

        <CatalogFilterBar
          searchValue={viewState.search ?? ""}
          source={viewState.source}
          triageStatus={viewState.triageStatus}
          analysisStatus={viewState.analysisStatus}
          monetization={viewState.monetization}
          minStars={viewState.minStars}
          maxStars={viewState.maxStars}
          sort={viewState.sort}
          order={viewState.order}
          visibleCount={data?.items.length ?? 0}
          totalCount={data?.total ?? 0}
          chips={activeFilterChips}
          isRefreshing={catalogQuery.isFetching}
          validationMessage={validationMessage}
          onSearchChange={handleSearchChange}
          onSourceChange={handleSourceChange}
          onTriageStatusChange={handleTriageStatusChange}
          onAnalysisStatusChange={handleAnalysisStatusChange}
          onMonetizationChange={handleMonetizationChange}
          onMinStarsChange={handleMinStarsChange}
          onMaxStarsChange={handleMaxStarsChange}
          onSortChange={handleSortChange}
          onOrderChange={handleOrderChange}
          onRemoveChip={handleRemoveChip}
          onClearAll={handleClearAll}
        />

        {validationMessage === null && catalogQuery.isLoading && !data ? (
          <section className="rounded-[2rem] border border-black/10 bg-white/90 px-6 py-16 text-center shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)]">
            <p className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">
              Loading
            </p>
            <h2 className="mt-3 text-2xl font-semibold text-slate-950">
              Fetching repository catalog
            </h2>
            <p className="mt-3 text-sm text-slate-600">
              Applying server-side filters and pagination.
            </p>
          </section>
        ) : null}

        {validationMessage === null && catalogQuery.isError ? (
          <section className="rounded-[2rem] border border-rose-200 bg-rose-50 px-6 py-12 shadow-[0_20px_60px_-36px_rgba(244,63,94,0.35)]">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-rose-700">
              Catalog Error
            </p>
            <h2 className="mt-3 text-2xl font-semibold text-rose-950">
              Unable to load repositories
            </h2>
            <p className="mt-3 max-w-2xl text-sm text-rose-900">{errorMessage}</p>
            <button
              className="mt-5 rounded-full border border-rose-300 bg-white px-4 py-2 text-sm font-semibold text-rose-900 transition hover:bg-rose-100"
              type="button"
              onClick={() => {
                void catalogQuery.refetch();
              }}
            >
              Retry fetch
            </button>
          </section>
        ) : null}

        {validationMessage === null && data && data.items.length === 0 && !catalogQuery.isError ? (
          <section className="rounded-[2rem] border border-black/10 bg-white/90 px-6 py-16 text-center shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)]">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
              Empty Result
            </p>
            <h2 className="mt-3 text-2xl font-semibold text-slate-950">
              No repositories match the current filters
            </h2>
            <p className="mt-3 text-sm text-slate-600">
              Remove one or more active filters to widen the catalog.
            </p>
          </section>
        ) : null}

        {validationMessage === null && data && data.items.length > 0 ? (
          <>
            <RepositoryCatalogTable
              items={data.items}
              onRowClick={(repositoryId) => {
                startTransition(() => {
                  router.push(`/repositories/${repositoryId}`);
                });
              }}
            />
            <CatalogPagination
              page={data.page}
              totalPages={data.total_pages}
              pageSize={data.page_size}
              totalCount={data.total}
              onPageChange={handlePageChange}
              onPageSizeChange={handlePageSizeChange}
            />
          </>
        ) : null}
      </div>
    </main>
  );
}

"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { startTransition } from "react";

import {
  type RepositoryCatalogPageResponse,
  buildRepositoryCatalogSearchParams,
  clearAllRepositoryCatalogFilters,
  clearRepositoryCatalogFilter,
  describeRepositoryCatalogFilters,
  fetchRepositoryCatalog,
  getRepositoryCatalogValidationMessage,
  getRepositoryCatalogQueryKey,
  getRepositoryDetailQueryKey,
  parseRepositoryCatalogSearchParams,
  updateRepositoryStar,
  type RepositoryAnalysisStatus,
  type RepositoryCatalogSortBy,
  type RepositoryCatalogSortOrder,
  type RepositoryDiscoverySource,
  type RepositoryMonetizationPotential,
  type RepositoryQueueStatus,
  type RepositoryTriageStatus,
} from "@/api/repositories";
import { BacklogSummaryBar } from "@/components/repositories/BacklogSummaryBar";
import { CatalogFilterBar } from "@/components/repositories/CatalogFilterBar";
import { CatalogPagination } from "@/components/repositories/CatalogPagination";
import { RepositoryCatalogTable } from "@/components/repositories/RepositoryCatalogTable";

function buildRepositoriesUrl(search: string): string {
  return search.length > 0 ? `/repositories?${search}` : "/repositories";
}

export function RepositoriesCatalogClient() {
  const queryClient = useQueryClient();
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

  const starMutation = useMutation({
    mutationFn: ({
      repositoryId,
      starred,
    }: {
      repositoryId: number;
      starred: boolean;
    }) => updateRepositoryStar(repositoryId, starred),
    onMutate: async ({ repositoryId, starred }) => {
      await queryClient.cancelQueries({ queryKey: ["repositories", "catalog"] });
      const previousPages = queryClient.getQueriesData<RepositoryCatalogPageResponse>({
        queryKey: ["repositories", "catalog"],
      });

      for (const [queryKey, page] of previousPages) {
        if (!page) {
          continue;
        }
        const starredOnly = queryKey[queryKey.length - 1] === true;
        const nextItems = page.items.flatMap((item) => {
          if (item.github_repository_id !== repositoryId) {
            return [item];
          }
          if (starredOnly && !starred) {
            return [];
          }
          return [{ ...item, is_starred: starred }];
        });
        const removedFromStarredView =
          starredOnly &&
          !starred &&
          page.items.some((item) => item.github_repository_id === repositoryId);

        queryClient.setQueryData<RepositoryCatalogPageResponse>(queryKey, {
          ...page,
          items: nextItems,
          total: removedFromStarredView ? Math.max(0, page.total - 1) : page.total,
          total_pages: removedFromStarredView
            ? Math.max(
                nextItems.length > 0 ? 1 : 0,
                Math.ceil(Math.max(0, page.total - 1) / page.page_size),
              )
            : page.total_pages,
        });
      }

      const previousDetail = queryClient.getQueryData(getRepositoryDetailQueryKey(repositoryId));
      queryClient.setQueryData(getRepositoryDetailQueryKey(repositoryId), (current) => {
        if (!current || typeof current !== "object") {
          return current;
        }
        return {
          ...current,
          is_starred: starred,
          starred_at: starred ? new Date().toISOString() : null,
        };
      });

      return { previousPages, previousDetail, repositoryId };
    },
    onError: (_error, _variables, context) => {
      if (!context) {
        return;
      }
      for (const [queryKey, page] of context.previousPages) {
        queryClient.setQueryData(queryKey, page);
      }
      queryClient.setQueryData(
        getRepositoryDetailQueryKey(context.repositoryId),
        context.previousDetail,
      );
    },
    onSettled: (_data, _error, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["repositories", "catalog"] });
      void queryClient.invalidateQueries({
        queryKey: getRepositoryDetailQueryKey(variables.repositoryId),
      });
    },
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

  const handleQueueStatusChange = (queueStatus: RepositoryQueueStatus | null) => {
    updateViewState({ queueStatus });
  };

  const handleTriageStatusChange = (triageStatus: RepositoryTriageStatus | null) => {
    updateViewState({ triageStatus });
  };

  const handleAnalysisStatusChange = (analysisStatus: RepositoryAnalysisStatus | null) => {
    updateViewState({ analysisStatus });
  };

  const handleHasFailuresChange = (hasFailures: boolean) => {
    updateViewState({ hasFailures });
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

  const handleStarredOnlyChange = (starredOnly: boolean) => {
    updateViewState({ starredOnly });
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
          queueStatus={viewState.queueStatus}
          triageStatus={viewState.triageStatus}
          analysisStatus={viewState.analysisStatus}
          hasFailures={viewState.hasFailures}
          monetization={viewState.monetization}
          minStars={viewState.minStars}
          maxStars={viewState.maxStars}
          starredOnly={viewState.starredOnly}
          sort={viewState.sort}
          order={viewState.order}
          visibleCount={data?.items.length ?? 0}
          totalCount={data?.total ?? 0}
          chips={activeFilterChips}
          isRefreshing={catalogQuery.isFetching}
          validationMessage={validationMessage}
          onSearchChange={handleSearchChange}
          onSourceChange={handleSourceChange}
          onQueueStatusChange={handleQueueStatusChange}
          onTriageStatusChange={handleTriageStatusChange}
          onAnalysisStatusChange={handleAnalysisStatusChange}
          onHasFailuresChange={handleHasFailuresChange}
          onMonetizationChange={handleMonetizationChange}
          onMinStarsChange={handleMinStarsChange}
          onMaxStarsChange={handleMaxStarsChange}
          onStarredOnlyChange={handleStarredOnlyChange}
          onSortChange={handleSortChange}
          onOrderChange={handleOrderChange}
          onRemoveChip={handleRemoveChip}
          onClearAll={handleClearAll}
        />

        <BacklogSummaryBar
          onSelectFilters={(patch) => {
            updateViewState({
              queueStatus: null,
              triageStatus: null,
              analysisStatus: null,
              hasFailures: false,
              ...patch,
            });
          }}
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
              onToggleStar={(repositoryId, starred) => {
                starMutation.mutate({ repositoryId, starred });
              }}
              togglingRepositoryId={starMutation.variables?.repositoryId ?? null}
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

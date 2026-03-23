"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { startTransition, useState } from "react";

import {
  buildRepositoryCatalogSearchParams,
  clearAllRepositoryCatalogFilters,
  clearRepositoryCatalogFilter,
  describeRepositoryCatalogFilters,
  fetchRepositoryCatalog,
  getRepositoryCatalogQueryKey,
  getRepositoryCatalogValidationMessage,
  getRepositoryDetailQueryKey,
  parseRepositoryCatalogSearchParams,
  updateRepositoryStar,
  type RepositoryAnalysisStatus,
  type RepositoryCatalogPageResponse,
  type RepositoryCatalogSortBy,
  type RepositoryCatalogSortOrder,
  type RepositoryCategory,
  type RepositoryDiscoverySource,
  type RepositoryMonetizationPotential,
  type RepositoryQueueStatus,
  type RepositoryTriageStatus,
} from "@/api/repositories";
import { FamilyFormDialog } from "@/components/ideas/FamilyFormDialog";
import { BacklogSummaryBar } from "@/components/repositories/BacklogSummaryBar";
import { CatalogFilterBar } from "@/components/repositories/CatalogFilterBar";
import { CatalogPagination } from "@/components/repositories/CatalogPagination";
import { RepositoryCatalogTable } from "@/components/repositories/RepositoryCatalogTable";
import { useAddRepositoryToFamily, useCreateIdeaFamily } from "@/hooks/useIdeaFamilies";

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
  const [selectedRepoIds, setSelectedRepoIds] = useState<Set<number>>(new Set());
  const [isFamilyDialogOpen, setIsFamilyDialogOpen] = useState(false);
  const createFamilyMutation = useCreateIdeaFamily();
  const addRepoMutation = useAddRepositoryToFamily();

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

  const handleCategoryChange = (category: RepositoryCategory | null) => {
    updateViewState({ category });
  };

  const handleAgentTagChange = (agentTag: string | null) => {
    updateViewState({ agentTag });
  };

  const handleUserTagChange = (userTag: string | null) => {
    updateViewState({ userTag });
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

  const handleMonetizationChange = (monetization: RepositoryMonetizationPotential | null) => {
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

  const handleCreateFamilyFromSelected = async (title: string, description: string | null) => {
    try {
      const family = await createFamilyMutation.mutateAsync({ title, description });
      const failures: number[] = [];

      for (const repoId of selectedRepoIds) {
        try {
          await addRepoMutation.mutateAsync({ familyId: family.id, repoId });
        } catch {
          failures.push(repoId);
        }
      }

      setSelectedRepoIds(new Set());
      setIsFamilyDialogOpen(false);

      if (failures.length > 0) {
        alert(
          `Family created, but failed to add ${failures.length} of ${selectedRepoIds.size} repositories. Please add them manually from the Ideas page.`,
        );
      }

      router.push(`/ideas?family=${family.id}`);
    } catch (error) {
      alert(`Failed to create family: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  };

  const data = validationMessage === null ? catalogQuery.data : undefined;
  const errorMessage =
    catalogQuery.error instanceof Error
      ? catalogQuery.error.message
      : "Unable to load repository catalog.";

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Repositories</span>
        {data && (
          <div style={{ display: "flex", gap: "10px", marginLeft: "auto" }}>
            <span className="badge badge-muted">{data.total.toLocaleString()} total</span>
            {viewState.starredOnly ? <span className="badge badge-yellow">Starred only</span> : null}
          </div>
        )}
      </div>

      <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden", padding: "20px" }}>
        <CatalogFilterBar
          searchValue={viewState.search ?? ""}
          source={viewState.source}
          category={viewState.category}
          agentTag={viewState.agentTag}
          userTag={viewState.userTag}
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
          onCategoryChange={handleCategoryChange}
          onAgentTagChange={handleAgentTagChange}
          onUserTagChange={handleUserTagChange}
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

        <div style={{ marginTop: "16px" }}>
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
        </div>

        {validationMessage === null && catalogQuery.isLoading && !data ? (
          <div className="card" style={{ marginTop: "16px", padding: "48px 24px", textAlign: "center" }}>
            <p className="card-label">Loading</p>
            <h2 className="card-title" style={{ marginTop: "8px", fontSize: "16px" }}>
              Fetching repository catalog
            </h2>
            <p style={{ marginTop: "8px", color: "var(--text-2)" }}>
              Applying server-side filters, curation tags, and taxonomy labels.
            </p>
          </div>
        ) : null}

        {validationMessage === null && catalogQuery.isError ? (
          <div className="card" style={{ marginTop: "16px", borderColor: "rgba(217, 79, 79, 0.28)", background: "var(--red-dim)" }}>
            <p className="card-label" style={{ color: "var(--red)" }}>
              Catalog Error
            </p>
            <h2 className="card-title" style={{ marginTop: "8px", fontSize: "16px" }}>
              Unable to load repositories
            </h2>
            <p style={{ marginTop: "8px", color: "var(--text-1)", maxWidth: "640px" }}>{errorMessage}</p>
            <button className="btn" style={{ marginTop: "14px" }} type="button" onClick={() => void catalogQuery.refetch()}>
              Retry fetch
            </button>
          </div>
        ) : null}

        {validationMessage === null && data && data.items.length === 0 && !catalogQuery.isError ? (
          <div className="card" style={{ marginTop: "16px", padding: "48px 24px", textAlign: "center" }}>
            <p className="card-label">Empty Result</p>
            <h2 className="card-title" style={{ marginTop: "8px", fontSize: "16px" }}>
              No repositories match the current filters
            </h2>
            <p style={{ marginTop: "8px", color: "var(--text-2)" }}>
              Remove one or more active filters to widen the catalog.
            </p>
          </div>
        ) : null}

        {validationMessage === null && data && data.items.length > 0 ? (
          <>
            {selectedRepoIds.size > 0 ? (
              <div className="card" style={{ marginTop: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px" }}>
                <div>
                  <p className="card-label">Selection Dock</p>
                  <p style={{ marginTop: "6px", color: "var(--text-0)" }}>
                    {selectedRepoIds.size} {selectedRepoIds.size === 1 ? "repository" : "repositories"} selected
                  </p>
                </div>
                <div style={{ display: "flex", gap: "8px" }}>
                  <button className="btn" type="button" onClick={() => setSelectedRepoIds(new Set())}>
                    Clear
                  </button>
                  <button className="btn btn-primary" type="button" onClick={() => setIsFamilyDialogOpen(true)}>
                    Create Family from Selected
                  </button>
                </div>
              </div>
            ) : null}

            <div style={{ marginTop: "16px" }}>
              <RepositoryCatalogTable
                items={data.items}
                selectedIds={selectedRepoIds}
                onToggleSelection={(repoId) => {
                  const next = new Set(selectedRepoIds);
                  if (next.has(repoId)) {
                    next.delete(repoId);
                  } else {
                    next.add(repoId);
                  }
                  setSelectedRepoIds(next);
                }}
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
            </div>

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

      <FamilyFormDialog
        isOpen={isFamilyDialogOpen}
        onClose={() => setIsFamilyDialogOpen(false)}
        family={null}
        onSubmit={handleCreateFamilyFromSelected}
      />
    </>
  );
}

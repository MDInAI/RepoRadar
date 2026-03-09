import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import {
  buildRepositoryCatalogSearchParams,
  parseRepositoryCatalogSearchParams,
  type RepositoryCatalogItem,
} from "@/api/repositories";
import { CatalogFilterBar } from "@/components/repositories/CatalogFilterBar";
import { RepositoryCatalogTable } from "@/components/repositories/RepositoryCatalogTable";

const BASE_ITEM: RepositoryCatalogItem = {
  github_repository_id: 701,
  full_name: "alpha/growth-engine",
  owner_login: "alpha",
  repository_name: "growth-engine",
  repository_description: "Growth workflows for operators",
  stargazers_count: 900,
  forks_count: 90,
  pushed_at: "2026-03-09T12:00:00Z",
  discovery_source: "firehose",
  queue_status: "completed",
  triage_status: "accepted",
  analysis_status: "completed",
  queue_created_at: "2026-03-09T12:00:00Z",
  processing_started_at: "2026-03-09T12:05:00Z",
  processing_completed_at: "2026-03-09T12:10:00Z",
  last_failed_at: null,
  analysis_failure_code: null,
  analysis_failure_message: null,
  monetization_potential: "high",
  has_readme_artifact: true,
  has_analysis_artifact: true,
  is_starred: false,
  user_tags: ["workflow"],
};

function renderCatalogTable(
  item: RepositoryCatalogItem,
  handlers?: {
    onToggleStar?: (repositoryId: number, starred: boolean) => void;
    onRowClick?: (repositoryId: number) => void;
  },
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <RepositoryCatalogTable
        items={[item]}
        onRowClick={handlers?.onRowClick ?? vi.fn()}
        onToggleStar={handlers?.onToggleStar ?? vi.fn()}
        togglingRepositoryId={null}
      />
    </QueryClientProvider>,
  );
}

describe("repository curation UI", () => {
  afterEach(() => {
    cleanup();
  });

  test("renders outline and filled star states and dispatches star toggles without row navigation", async () => {
    const user = userEvent.setup();
    const onToggleStar = vi.fn();
    const onRowClick = vi.fn();

    const { rerender } = renderCatalogTable(BASE_ITEM, { onToggleStar, onRowClick });

    const outlineButton = screen.getByRole("button", { name: "Star repository" });
    expect(outlineButton.getAttribute("aria-pressed")).toBe("false");
    await user.click(outlineButton);

    expect(onToggleStar).toHaveBeenCalledWith(701, true);
    expect(onRowClick).not.toHaveBeenCalled();

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    rerender(
      <QueryClientProvider client={queryClient}>
        <RepositoryCatalogTable
          items={[{ ...BASE_ITEM, is_starred: true }]}
          onRowClick={onRowClick}
          onToggleStar={onToggleStar}
          togglingRepositoryId={null}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("button", { name: "Unstar repository" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  test("shows the starred filter control and round-trips it through URL params", async () => {
    const user = userEvent.setup();
    const onStarredOnlyChange = vi.fn();

    render(
      <CatalogFilterBar
        searchValue=""
        source={null}
        queueStatus={null}
        triageStatus={null}
        analysisStatus={null}
        hasFailures={false}
        monetization={null}
        minStars={null}
        maxStars={null}
        starredOnly={false}
        sort="stars"
        order="desc"
        visibleCount={1}
        totalCount={10}
        chips={[]}
        isRefreshing={false}
        validationMessage={null}
        onSearchChange={vi.fn()}
        onSourceChange={vi.fn()}
        onQueueStatusChange={vi.fn()}
        onTriageStatusChange={vi.fn()}
        onAnalysisStatusChange={vi.fn()}
        onHasFailuresChange={vi.fn()}
        onMonetizationChange={vi.fn()}
        onMinStarsChange={vi.fn()}
        onMaxStarsChange={vi.fn()}
        onStarredOnlyChange={onStarredOnlyChange}
        onSortChange={vi.fn()}
        onOrderChange={vi.fn()}
        onRemoveChip={vi.fn()}
        onClearAll={vi.fn()}
      />,
    );

    await user.click(screen.getByLabelText("Show starred only"));
    expect(onStarredOnlyChange).toHaveBeenCalledWith(true);

    const params = buildRepositoryCatalogSearchParams({
      page: 1,
      pageSize: 30,
      sort: "stars",
      order: "desc",
      search: null,
      source: null,
      queueStatus: null,
      triageStatus: null,
      analysisStatus: null,
      hasFailures: false,
      monetization: null,
      minStars: null,
      maxStars: null,
      starredOnly: true,
    });
    expect(params.get("starredOnly")).toBe("true");

    const parsed = parseRepositoryCatalogSearchParams(params);
    expect(parsed.starredOnly).toBe(true);
  });
});

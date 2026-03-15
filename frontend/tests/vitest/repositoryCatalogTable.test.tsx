import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { RepositoryCatalogItem } from "@/api/repositories";
import { RepositoryCatalogTable } from "@/components/repositories/RepositoryCatalogTable";

const ITEM: RepositoryCatalogItem = {
  github_repository_id: 701,
  full_name: "alpha/growth-engine",
  owner_login: "alpha",
  repository_name: "growth-engine",
  repository_description: "Growth workflows for operators",
  stargazers_count: 900,
  forks_count: 90,
  pushed_at: "2026-03-09T12:00:00Z",
  discovery_source: "firehose",
  firehose_discovery_mode: "trending",
  intake_status: "completed",
  triage_status: "accepted",
  analysis_status: "completed",
  queue_created_at: "2026-03-09T12:00:00Z",
  processing_started_at: "2026-03-09T12:05:00Z",
  processing_completed_at: "2026-03-09T12:10:00Z",
  intake_failed_at: null,
  analysis_failed_at: null,
  failure: null,
  category: "workflow",
  agent_tags: ["workflow", "automation"],
  monetization_potential: "high",
  has_readme_artifact: true,
  has_analysis_artifact: true,
  is_starred: false,
  user_tags: ["workflow"],
};

function renderTable(
  onRowClick: (repositoryId: number) => void,
  onToggleStar: (repositoryId: number, starred: boolean) => void = vi.fn(),
  items: RepositoryCatalogItem[] = [ITEM],
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <RepositoryCatalogTable
        items={items}
        onRowClick={onRowClick}
        onToggleStar={onToggleStar}
        togglingRepositoryId={null}
      />
    </QueryClientProvider>,
  );
}

describe("RepositoryCatalogTable", () => {
  afterEach(() => {
    cleanup();
  });

  test("renders repository data with the required columns", () => {
    renderTable(vi.fn());

    expect(screen.getByText("alpha/growth-engine")).toBeTruthy();
    expect(screen.getByText("Growth workflows for operators")).toBeTruthy();
    expect(screen.getByText("Category")).toBeTruthy();
    expect(screen.getAllByText("Workflow").length).toBeGreaterThan(0);
    expect(screen.getByText("Agent Tags")).toBeTruthy();
    expect(screen.getByText("User Tags")).toBeTruthy();
    expect(screen.getByText("Firehose")).toBeTruthy();
    expect(screen.getByText("Accepted")).toBeTruthy();
    expect(screen.getAllByText("workflow").length).toBeGreaterThan(0);
    expect(screen.getByText("automation")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Star repository" })).toBeTruthy();
  });

  test("routes row clicks through the provided handler", async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();

    renderTable(onRowClick);
    await user.click(screen.getAllByText("alpha/growth-engine")[0]!);

    expect(onRowClick).toHaveBeenCalledWith(701);
  });

  test("shows analysis status and empty user tags cleanly", () => {
    const failedItem: RepositoryCatalogItem = {
      ...ITEM,
      analysis_status: "failed",
      user_tags: [],
    };

    renderTable(vi.fn(), vi.fn(), [failedItem]);

    expect(screen.getByText("Failed")).toBeTruthy();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  test("renders selection controls when provided", async () => {
    const user = userEvent.setup();
    const onToggleSelection = vi.fn();
    const selectableItem: RepositoryCatalogItem = {
      ...ITEM,
      github_repository_id: 702,
    };

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <RepositoryCatalogTable
          items={[selectableItem]}
          selectedIds={new Set()}
          onToggleSelection={onToggleSelection}
          onRowClick={vi.fn()}
          onToggleStar={vi.fn()}
          togglingRepositoryId={null}
        />
      </QueryClientProvider>,
    );

    await user.click(screen.getByLabelText("Select alpha/growth-engine"));
    expect(onToggleSelection).toHaveBeenCalledWith(702);
  });
});

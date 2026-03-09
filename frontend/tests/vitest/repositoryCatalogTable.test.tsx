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
    expect(screen.getByText("Monetization Fit")).toBeTruthy();
    expect(screen.getByText("High")).toBeTruthy();
    expect(screen.getByText("Firehose")).toBeTruthy();
    expect(screen.getByText("Queue Status")).toBeTruthy();
    expect(screen.getByText("Failure Details")).toBeTruthy();
    expect(screen.getAllByText("Completed")).toHaveLength(2);
    expect(screen.getByText("No failures")).toBeTruthy();
    expect(screen.getByText("workflow")).toBeTruthy();
  });

  test("routes row clicks through the provided handler", async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();

    renderTable(onRowClick);
    await user.click(screen.getAllByText("alpha/growth-engine")[0]!);

    expect(onRowClick).toHaveBeenCalledWith(701);
  });

  test("shows analysis failure code, message, and timestamp", () => {
    const failedItem: RepositoryCatalogItem = {
      ...ITEM,
      analysis_status: "failed",
      analysis_failure_code: "rate_limited",
      analysis_failure_message: "Gateway rate limit while analyzing repository.",
      last_failed_at: "2026-03-09T12:15:00Z",
    };

    renderTable(vi.fn(), vi.fn(), [failedItem]);

    expect(screen.getByText("Analysis Failure")).toBeTruthy();
    expect(screen.getByText("Failure: Rate Limited")).toBeTruthy();
    expect(screen.getByText("Rate Limited")).toBeTruthy();
    expect(screen.getByText("Gateway rate limit while analyzing repository.")).toBeTruthy();
    expect(screen.getByText("Failed At 2026-03-09 12:15 UTC")).toBeTruthy();
  });

  test("shows queue failure fallback details when analysis metadata is missing", () => {
    const failedItem: RepositoryCatalogItem = {
      ...ITEM,
      queue_status: "failed",
      analysis_status: "pending",
      analysis_failure_code: null,
      analysis_failure_message: null,
      last_failed_at: "2026-03-09T12:20:00Z",
    };

    renderTable(vi.fn(), vi.fn(), [failedItem]);

    expect(screen.getByText("Queue Failure")).toBeTruthy();
    expect(screen.getByText("Queue Failed")).toBeTruthy();
    expect(screen.getByText("Repository intake failed before analysis completed.")).toBeTruthy();
    expect(screen.getByText("Failed At 2026-03-09 12:20 UTC")).toBeTruthy();
  });
});

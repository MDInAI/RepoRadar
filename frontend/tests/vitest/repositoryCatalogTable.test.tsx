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
  triage_status: "accepted",
  analysis_status: "completed",
  monetization_potential: "high",
  has_readme_artifact: true,
  has_analysis_artifact: true,
};

function renderTable(onRowClick: (repositoryId: number) => void) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <RepositoryCatalogTable items={[ITEM]} onRowClick={onRowClick} />
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
    expect(screen.getByText("Completed")).toBeTruthy();
  });

  test("routes row clicks through the provided handler", async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();

    renderTable(onRowClick);
    await user.click(screen.getAllByText("alpha/growth-engine")[0]!);

    expect(onRowClick).toHaveBeenCalledWith(701);
  });
});

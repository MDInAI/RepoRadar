import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import RepositoriesPage from "@/app/repositories/page";

const mockPush = vi.fn();
const mockReplace = vi.fn();
let currentSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
  }),
  useSearchParams: () => currentSearchParams,
}));

const catalogResponse = {
  items: [
    {
      github_repository_id: 701,
      full_name: "alpha/growth-engine",
      owner_login: "alpha",
      repository_name: "growth-engine",
      repository_description: "Growth workflows for operators",
      stargazers_count: 900,
      forks_count: 90,
      pushed_at: "2026-03-09T12:00:00Z",
      discovery_source: "firehose",
      intake_status: "completed",
      triage_status: "accepted",
      analysis_status: "completed",
      queue_created_at: "2026-03-09T12:00:00Z",
      processing_started_at: "2026-03-09T12:05:00Z",
      processing_completed_at: "2026-03-09T12:10:00Z",
      intake_failed_at: null,
      analysis_failed_at: null,
      failure: null,
      monetization_potential: "high",
      has_readme_artifact: true,
      has_analysis_artifact: true,
      is_starred: false,
      user_tags: ["workflow"],
    },
  ],
  total: 1,
  page: 1,
  page_size: 30,
  total_pages: 1,
};

const backlogSummaryResponse = {
  queue: { pending: 3, in_progress: 2, completed: 10, failed: 1 },
  triage: { pending: 4, accepted: 8, rejected: 2 },
  analysis: { pending: 5, in_progress: 1, completed: 7, failed: 2 },
};

function renderPage(responseOverride?: Partial<typeof catalogResponse>) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  const responseBody = {
    ...catalogResponse,
    ...responseOverride,
  };

  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : input.toString();
    const body = url.includes("/backlog/summary") ? backlogSummaryResponse : responseBody;
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
      },
    });
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <RepositoriesPage />
    </QueryClientProvider>,
  );
}

describe("RepositoriesPage", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://api.test";
    currentSearchParams = new URLSearchParams("search=growth&source=firehose");
    mockPush.mockReset();
    mockReplace.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  test("shows active filter chips and removes them through URL params", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("alpha/growth-engine")).toBeTruthy();
    expect(screen.getByLabelText("Remove Search: growth filter")).toBeTruthy();
    expect(screen.getByLabelText("Remove Source: Firehose filter")).toBeTruthy();

    await user.click(screen.getByLabelText("Remove Source: Firehose filter"));

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/repositories?search=growth", {
        scroll: false,
      });
    });
  });

  test("syncs filter, sort, and pagination controls back into URL params", async () => {
    const user = userEvent.setup();
    currentSearchParams = new URLSearchParams();
    renderPage();

    expect(await screen.findByText("alpha/growth-engine")).toBeTruthy();

    await user.selectOptions(screen.getAllByLabelText("Discovery source")[0]!, "backfill");
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?source=backfill", {
        scroll: false,
      });
    });

    await user.selectOptions(screen.getAllByLabelText("Sort by")[0]!, "forks");
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?sort=forks", {
        scroll: false,
      });
    });

    await user.selectOptions(screen.getAllByLabelText("Rows per page")[0]!, "50");
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?pageSize=50", {
        scroll: false,
      });
    });
  });

  test("syncs the remaining filter controls and sort order back into URL params", async () => {
    const user = userEvent.setup();
    currentSearchParams = new URLSearchParams();
    renderPage();

    expect(await screen.findByText("alpha/growth-engine")).toBeTruthy();

    const searchInput = screen.getByLabelText("Search repositories");
    fireEvent.change(searchInput, { target: { value: "pipeline" } });
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?search=pipeline", {
        scroll: false,
      });
    });

    mockReplace.mockClear();
    await user.selectOptions(screen.getByLabelText("Queue status"), "failed");
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?queueStatus=failed", {
        scroll: false,
      });
    });

    mockReplace.mockClear();
    await user.selectOptions(screen.getByLabelText("Triage status"), "pending");
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?triageStatus=pending", {
        scroll: false,
      });
    });

    mockReplace.mockClear();
    await user.selectOptions(screen.getByLabelText("Analysis status"), "failed");
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?analysisStatus=failed", {
        scroll: false,
      });
    });

    mockReplace.mockClear();
    await user.selectOptions(screen.getByLabelText("Monetization fit"), "medium");
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?monetization=medium", {
        scroll: false,
      });
    });

    mockReplace.mockClear();
    fireEvent.change(screen.getByLabelText("Minimum stars"), {
      target: { value: "150" },
    });
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?minStars=150", {
        scroll: false,
      });
    });

    mockReplace.mockClear();
    fireEvent.change(screen.getByLabelText("Maximum stars"), {
      target: { value: "500" },
    });
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?maxStars=500", {
        scroll: false,
      });
    });

    mockReplace.mockClear();
    await user.click(screen.getByLabelText("Show failures only"));
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?hasFailures=true", {
        scroll: false,
      });
    });

    mockReplace.mockClear();
    await user.click(screen.getByLabelText("Toggle sort order"));
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?order=asc", {
        scroll: false,
      });
    });
  });

  test("syncs previous and next pagination buttons back into URL params", async () => {
    const user = userEvent.setup();
    currentSearchParams = new URLSearchParams("page=2");
    renderPage({
      page: 2,
      total: 90,
      total_pages: 3,
    });

    expect(await screen.findByText("alpha/growth-engine")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?page=3", {
        scroll: false,
      });
    });

    mockReplace.mockClear();
    await user.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories", {
        scroll: false,
      });
    });
  });

  test("navigates to repository detail on row click", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("alpha/growth-engine"));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/repositories/701");
    });
  });

  test("blocks catalog fetches when the star range is invalid and shows inline guidance", async () => {
    currentSearchParams = new URLSearchParams("minStars=500&maxStars=400");
    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText("Minimum stars cannot exceed maximum stars."),
      ).toBeTruthy();
    });

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://api.test/api/v1/repositories/backlog/summary",
      { cache: "no-store" },
    );
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createElement } from "react";
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

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : input.toString();
    const body = url.includes("/backlog/summary") ? backlogSummaryResponse : catalogResponse;
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  return render(
    createElement(
      QueryClientProvider,
      { client: queryClient },
      createElement(RepositoriesPage),
    ),
  );
}

describe("BacklogSummaryBar", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://api.test";
    currentSearchParams = new URLSearchParams();
    mockPush.mockReset();
    mockReplace.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  test("renders backlog counts with semantic badge styling", async () => {
    renderPage();

    const failedAnalysisBadge = await screen.findByLabelText(
      "2 repositories with failed analysis",
    );
    const completedQueueBadge = screen.getByLabelText(
      "10 repositories with completed queue status",
    );

    expect(failedAnalysisBadge.textContent).toContain("2");
    expect(failedAnalysisBadge.className).toContain("border-rose-300");
    expect(completedQueueBadge.className).toContain("border-emerald-300");
  });

  test("clicking summary badges and backlog filters updates repository URL params", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByLabelText("2 repositories with failed analysis"));
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?analysisStatus=failed", {
        scroll: false,
      });
    });

    mockReplace.mockClear();
    expect(screen.getByLabelText("Queue status")).toBeTruthy();

    await user.selectOptions(screen.getByLabelText("Queue status"), "pending");
    await waitFor(() => {
      expect(mockReplace).toHaveBeenLastCalledWith("/repositories?queueStatus=pending", {
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
  });
});

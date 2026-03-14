import { render, screen, cleanup, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import OverviewPage from "@/app/overview/page";

vi.mock("@/hooks/useEventStream", () => ({
  useEventStream: vi.fn(),
}));

const mockSummaryData = {
  ingestion: { total_repositories: 100, pending_intake: 10, firehose_discovered: 50, backfill_discovered: 50 },
  triage: { pending: 5, accepted: 80, rejected: 15 },
  analysis: { pending: 20, in_progress: 10, completed: 50, failed: 0 },
  backlog: {
    queue_pending: 10, queue_in_progress: 5, queue_completed: 85, queue_failed: 0,
    triage_pending: 5, triage_accepted: 80, triage_rejected: 15,
    analysis_pending: 20, analysis_in_progress: 10, analysis_completed: 50, analysis_failed: 0,
  },
  agents: [],
  failures: { total_failures: 2, critical_failures: 0, rate_limited_failures: 1, blocking_failures: 0 },
};

vi.mock("@/api/overview", () => ({
  fetchOverviewSummary: vi.fn(() => Promise.resolve(mockSummaryData)),
  getOverviewSummaryQueryKey: vi.fn(() => ["overview", "summary"]),
}));

vi.mock("@/api/agents", () => ({
  fetchLatestAgentRuns: vi.fn(() => Promise.resolve({ agents: [] })),
  fetchAgentPauseStates: vi.fn(() => Promise.resolve([])),
  getLatestAgentRunsQueryKey: vi.fn(() => ["agents", "latest-runs"]),
  getAgentPauseStatesQueryKey: vi.fn(() => ["agents", "pause-states"]),
  sortAgentStatusEntries: vi.fn((entries: any[]) => entries),
  AGENT_DISPLAY_ORDER: ["overlord", "firehose", "backfill", "bouncer", "analyst"],
}));

describe("OverviewPage", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders metric cards for ingestion", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <OverviewPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Ingestion")).toBeInTheDocument();
    });

    const ingestionSection = screen.getByText("Ingestion").closest("div");
    expect(ingestionSection).toBeInTheDocument();

    // Verify total repositories metric
    const totalReposLabel = screen.getByText("Total Repositories");
    expect(totalReposLabel).toBeInTheDocument();
    const totalReposValue = totalReposLabel.parentElement?.querySelector("p.text-3xl");
    expect(totalReposValue).toHaveTextContent("100");

    // Verify pending intake metric
    const pendingLabel = screen.getByText("Pending Intake");
    expect(pendingLabel).toBeInTheDocument();
    const pendingValue = pendingLabel.parentElement?.querySelector("p.text-3xl");
    expect(pendingValue).toHaveTextContent("10");
  });

  it("renders quick action links", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <OverviewPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Manage Agents")).toBeInTheDocument();
    });

    expect(screen.getByText("View Incidents")).toBeInTheDocument();
    expect(screen.getByText("Browse Repositories")).toBeInTheDocument();
  });

  it("renders agent status matrix", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <OverviewPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Agent Health & Control")).toBeInTheDocument();
    });
  });
});

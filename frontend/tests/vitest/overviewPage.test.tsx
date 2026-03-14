import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OverviewPage from "@/app/overview/page";

const mockSummaryData = {
  ingestion: {
    total_repositories: 100,
    pending_intake: 10,
    firehose_discovered: 50,
    backfill_discovered: 50,
    discovered_last_24h: 18,
    firehose_discovered_last_24h: 12,
    backfill_discovered_last_24h: 6,
  },
  triage: { pending: 5, accepted: 80, rejected: 15 },
  analysis: { pending: 20, in_progress: 10, completed: 50, failed: 0 },
  backlog: {
    queue_pending: 10,
    queue_in_progress: 5,
    queue_completed: 85,
    queue_failed: 0,
    triage_pending: 5,
    triage_accepted: 80,
    triage_rejected: 15,
    analysis_pending: 20,
    analysis_in_progress: 10,
    analysis_completed: 50,
    analysis_failed: 0,
  },
  agents: [
    {
      agent_name: "firehose",
      display_name: "Firehose",
      role_label: "Repository intake",
      description: "Discovers repositories.",
      implementation_status: "live",
      runtime_kind: "github-api-worker",
      uses_github_token: true,
      uses_model: false,
      configured_provider: "github",
      configured_model: null,
      notes: [],
      status: "completed",
      is_paused: false,
      last_run_at: null,
      token_usage_24h: 0,
      input_tokens_24h: 0,
      output_tokens_24h: 0,
    },
    {
      agent_name: "combiner",
      display_name: "Combiner",
      role_label: "Opportunity synthesis",
      description: "Synthesizes opportunities from prior analysis.",
      implementation_status: "live",
      runtime_kind: "llm-synthesis",
      uses_github_token: false,
      uses_model: true,
      configured_provider: "anthropic",
      configured_model: "claude-3-5-sonnet-20241022",
      notes: [],
      status: "completed",
      is_paused: false,
      last_run_at: null,
      token_usage_24h: 1800,
      input_tokens_24h: 1200,
      output_tokens_24h: 600,
    },
  ],
  failures: { total_failures: 2, critical_failures: 0, rate_limited_failures: 1, blocking_failures: 0 },
  token_usage: {
    total_tokens_24h: 1800,
    input_tokens_24h: 1200,
    output_tokens_24h: 600,
    llm_runs_24h: 1,
    top_consumer_agent_name: "combiner",
    top_consumer_tokens_24h: 1800,
  },
};

vi.mock("@/api/overview", () => ({
  fetchOverviewSummary: vi.fn(() => Promise.resolve(mockSummaryData)),
  getOverviewSummaryQueryKey: vi.fn(() => ["overview", "summary"]),
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

  it("renders the mission control hero and real token burn card", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <OverviewPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Mission Control")).toBeInTheDocument();
    expect(screen.getByText("Token Burn (24h)")).toBeInTheDocument();
    expect(screen.getByText("1.8K")).toBeInTheDocument();
    expect(screen.getByText("Tracked")).toBeInTheDocument();
    expect(screen.getByText("Combiner used 1.8K in the last 24h")).toBeInTheDocument();
  });

  it("renders pipeline flow and system health metrics", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <OverviewPage />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("System Health")).toBeInTheDocument();
    });

    expect(screen.getByText("Repos Discovered (24h)")).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("12 firehose · 6 backfill")).toBeInTheDocument();
    expect(screen.getByText("Pipeline Flow")).toBeInTheDocument();
    expect(screen.getByText("Ideas DB")).toBeInTheDocument();
  });

  it("renders truth-based agent function cards", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <OverviewPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Agent Functions")).toBeInTheDocument();
    expect(screen.getByText("Provider: github")).toBeInTheDocument();
    expect(screen.getByText("Model: none")).toBeInTheDocument();
    expect(screen.getByText("Provider: anthropic")).toBeInTheDocument();
    expect(screen.getByText("Model: claude-3-5-sonnet-20241022")).toBeInTheDocument();
    expect(screen.getByText("GitHub API")).toBeInTheDocument();
    expect(screen.getByText("AI")).toBeInTheDocument();
  });
});

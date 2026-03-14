import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import AgentsClient from "@/app/agents/AgentsClient";

const latestRunsResponse = {
  agents: [
    {
      agent_name: "overlord",
      display_name: "Overlord",
      role_label: "Control-plane coordinator",
      description: "Control-plane placeholder.",
      implementation_status: "placeholder",
      runtime_kind: "control-plane-placeholder",
      uses_github_token: false,
      uses_model: false,
      configured_provider: null,
      configured_model: null,
      notes: ["No standalone worker loop currently executes Overlord jobs."],
      token_usage_24h: 0,
      input_tokens_24h: 0,
      output_tokens_24h: 0,
      has_run: false,
      latest_run: null,
    },
    {
      agent_name: "firehose",
      display_name: "Firehose",
      role_label: "Repository intake",
      description: "Discovers repositories from GitHub feeds.",
      implementation_status: "live",
      runtime_kind: "github-api-worker",
      uses_github_token: true,
      uses_model: false,
      configured_provider: "github",
      configured_model: null,
      notes: ["Uses GITHUB_PROVIDER_TOKEN for GitHub API requests."],
      token_usage_24h: 0,
      input_tokens_24h: 0,
      output_tokens_24h: 0,
      has_run: true,
      latest_run: {
        id: 11,
        agent_name: "firehose",
        status: "completed",
        started_at: "2026-03-10T10:00:00Z",
        completed_at: "2026-03-10T10:04:00Z",
        duration_seconds: 240,
        items_processed: 12,
        items_succeeded: 12,
        items_failed: 0,
        error_summary: null,
        provider_name: "github",
        model_name: null,
        input_tokens: 0,
        output_tokens: 0,
        total_tokens: 0,
      },
    },
    {
      agent_name: "backfill",
      display_name: "Backfill",
      role_label: "Historical intake",
      description: "Replays older GitHub windows.",
      implementation_status: "live",
      runtime_kind: "github-api-worker",
      uses_github_token: true,
      uses_model: false,
      configured_provider: "github",
      configured_model: null,
      notes: [],
      token_usage_24h: 0,
      input_tokens_24h: 0,
      output_tokens_24h: 0,
      has_run: false,
      latest_run: null,
    },
    {
      agent_name: "bouncer",
      display_name: "Bouncer",
      role_label: "Rule-based triage",
      description: "Applies local include and exclude rules.",
      implementation_status: "live",
      runtime_kind: "rules-engine",
      uses_github_token: false,
      uses_model: false,
      configured_provider: "local-rules",
      configured_model: null,
      notes: [],
      token_usage_24h: 0,
      input_tokens_24h: 0,
      output_tokens_24h: 0,
      has_run: true,
      latest_run: {
        id: 12,
        agent_name: "bouncer",
        status: "running",
        started_at: "2026-03-10T10:05:00Z",
        completed_at: null,
        duration_seconds: null,
        items_processed: 4,
        items_succeeded: 4,
        items_failed: 0,
        error_summary: null,
        provider_name: "local-rules",
        model_name: null,
        input_tokens: 0,
        output_tokens: 0,
        total_tokens: 0,
      },
    },
    {
      agent_name: "analyst",
      display_name: "Analyst",
      role_label: "README analysis",
      description: "Fetches README content and scores it heuristically.",
      implementation_status: "live",
      runtime_kind: "heuristic-analysis",
      uses_github_token: true,
      uses_model: false,
      configured_provider: "heuristic-readme-analysis",
      configured_model: null,
      notes: ["Current implementation uses HeuristicReadmeAnalysisProvider, not an LLM."],
      token_usage_24h: 0,
      input_tokens_24h: 0,
      output_tokens_24h: 0,
      has_run: false,
      latest_run: null,
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
      notes: ["Uses Anthropic when ANTHROPIC_API_KEY is configured."],
      token_usage_24h: 1800,
      input_tokens_24h: 1200,
      output_tokens_24h: 600,
      has_run: false,
      latest_run: null,
    },
    {
      agent_name: "obsession",
      display_name: "Obsession",
      role_label: "Context tracking",
      description: "Tracks obsession contexts and refresh triggers.",
      implementation_status: "partial",
      runtime_kind: "workflow-state",
      uses_github_token: false,
      uses_model: false,
      configured_provider: "workflow-state",
      configured_model: null,
      notes: ["Any model usage currently happens downstream rather than directly here."],
      token_usage_24h: 0,
      input_tokens_24h: 0,
      output_tokens_24h: 0,
      has_run: false,
      latest_run: null,
    },
  ],
};

const agentRunsResponse = [
  {
    id: 12,
    agent_name: "bouncer",
    status: "running",
    started_at: "2026-03-10T10:05:00Z",
    completed_at: null,
    duration_seconds: null,
    items_processed: 4,
    items_succeeded: 4,
    items_failed: 0,
    error_summary: null,
    provider_name: "local-rules",
    model_name: null,
    input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
  },
  {
    id: 11,
    agent_name: "firehose",
    status: "completed",
    started_at: "2026-03-10T10:00:00Z",
    completed_at: "2026-03-10T10:04:00Z",
    duration_seconds: 240,
    items_processed: 12,
    items_succeeded: 12,
    items_failed: 0,
    error_summary: "Recovered after backoff",
    provider_name: "github",
    model_name: null,
    input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
  },
];

const pauseStatesResponse = [
  {
    id: 1,
    agent_name: "firehose",
    is_paused: true,
    paused_at: "2026-03-10T10:00:00Z",
    pause_reason: "GitHub rate limit exceeded",
    resume_condition: "Rate limit window expires at 2026-03-10T11:00:00Z",
    triggered_by_event_id: 91,
    resumed_at: null,
    resumed_by: null,
  },
];

function renderClient() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof Request
          ? input.url
          : input.toString();
    const body = url.includes("/agents/runs/latest")
      ? latestRunsResponse
      : url.includes("/agents/pause-state")
        ? pauseStatesResponse
        : agentRunsResponse;

    return new Response(JSON.stringify(body), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
      },
    });
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <AgentsClient />
    </QueryClientProvider>,
  );
}

describe("AgentsClient", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://api.test";
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  test("renders the new roster and details panel", async () => {
    renderClient();

    expect(await screen.findByText("Agent Management")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByTestId(/agent-roster-card-/)).toHaveLength(7);
    });
    const details = screen.getByTestId("agent-details-panel");
    expect(details).toBeInTheDocument();
    expect(within(details).getByText("Control-plane coordinator")).toBeInTheDocument();
  });

  test("renders run history columns and error summary", async () => {
    renderClient();

    expect(await screen.findByText("Run History")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Agent" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Started" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Duration" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Items" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Error Summary" })).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.getByText((content) => content.includes("Recovered after backoff")),
      ).toBeInTheDocument();
    });
  });

  test("shows real provider and token usage metadata for a model-backed agent", async () => {
    renderClient();

    const combinerCard = await screen.findByTestId("agent-roster-card-combiner");
    fireEvent.click(combinerCard);

    const details = screen.getByTestId("agent-details-panel");
    expect(within(details).getByText("anthropic")).toBeInTheDocument();
    expect(within(details).getByText("claude-3-5-sonnet-20241022")).toBeInTheDocument();
    expect(screen.getByText("1.8K")).toBeInTheDocument();
    expect(
      screen.getByText("Latest provider: anthropic"),
    ).toBeInTheDocument();
  });

  test("shows truth-based runtime notes for a non-model agent", async () => {
    renderClient();

    const analystCard = await screen.findByTestId("agent-roster-card-analyst");
    fireEvent.click(analystCard);

    const details = await screen.findByTestId("agent-details-panel");
    expect(within(details).getByText("README analysis")).toBeInTheDocument();
    expect(
      screen.getByText("Current implementation uses HeuristicReadmeAnalysisProvider, not an LLM."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No model-backed usage is expected for this agent in the current runtime."),
    ).toBeInTheDocument();
  });
});

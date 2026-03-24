import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OverviewPage from "@/app/overview/page";

const mockOverviewSummary = {
  ingestion: {
    total_repositories: 120,
    pending_intake: 14,
    firehose_discovered: 70,
    backfill_discovered: 50,
    discovered_last_24h: 21,
    firehose_discovered_last_24h: 13,
    backfill_discovered_last_24h: 8,
  },
  triage: { pending: 6, accepted: 84, rejected: 30 },
  analysis: { pending: 5, in_progress: 2, completed: 77, failed: 1 },
  backlog: {
    queue_pending: 14,
    queue_in_progress: 2,
    queue_completed: 104,
    queue_failed: 0,
    triage_pending: 6,
    triage_accepted: 84,
    triage_rejected: 30,
    analysis_pending: 5,
    analysis_in_progress: 2,
    analysis_completed: 77,
    analysis_failed: 1,
  },
  agents: [],
  failures: { total_failures: 2, critical_failures: 1, rate_limited_failures: 0, blocking_failures: 1 },
  token_usage: {
    total_tokens_24h: 2500,
    input_tokens_24h: 1800,
    output_tokens_24h: 700,
    llm_runs_24h: 2,
    top_consumer_agent_name: "analyst",
    top_consumer_tokens_24h: 1800,
  },
};

const mockLatestRuns = {
  agents: [
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
      notes: [],
      token_usage_24h: 0,
      input_tokens_24h: 0,
      output_tokens_24h: 0,
      has_run: true,
      latest_run: {
        id: 11,
        agent_name: "firehose",
        status: "failed",
        started_at: "2026-03-18T08:00:00Z",
        completed_at: "2026-03-18T08:03:00Z",
        duration_seconds: 180,
        items_processed: 4,
        items_succeeded: 3,
        items_failed: 1,
        error_summary: "Provider failed during intake batch",
        provider_name: "github",
        model_name: null,
        input_tokens: 0,
        output_tokens: 0,
        total_tokens: 0,
      },
      latest_intake_summary: null,
      runtime_progress: {
        status_label: "Idle",
        current_activity: "Waiting for the next Firehose cycle.",
        current_target: "Mode NEW, next page 4",
        progress_percent: 75,
        primary_counts_label: "Pages completed",
        completed_count: 3,
        total_count: 4,
        remaining_count: 1,
        unit_label: "pages",
        secondary_counts_label: null,
        secondary_completed_count: null,
        secondary_total_count: null,
        secondary_remaining_count: null,
        secondary_unit_label: null,
        updated_at: "2026-03-18T08:03:00Z",
        source: "firehose checkpoint + intake queue",
        details: ["Pending discovered repos: 14", "Completed discoveries: 70"],
      },
    },
    {
      agent_name: "analyst",
      display_name: "Analyst",
      role_label: "README analysis",
      description: "Analyzes accepted repositories.",
      implementation_status: "live",
      runtime_kind: "queue-worker",
      uses_github_token: true,
      uses_model: true,
      configured_provider: "gemini",
      configured_model: "gemini-pro",
      notes: [],
      token_usage_24h: 2500,
      input_tokens_24h: 1800,
      output_tokens_24h: 700,
      has_run: true,
      latest_run: {
        id: 22,
        agent_name: "analyst",
        status: "completed",
        started_at: "2026-03-18T07:00:00Z",
        completed_at: "2026-03-18T07:06:00Z",
        duration_seconds: 360,
        items_processed: 8,
        items_succeeded: 8,
        items_failed: 0,
        error_summary: null,
        provider_name: "gemini",
        model_name: "gemini-pro",
        input_tokens: 1200,
        output_tokens: 400,
        total_tokens: 1600,
      },
      latest_intake_summary: null,
      runtime_progress: {
        status_label: "Idle",
        current_activity: "Waiting for accepted repositories that need analysis.",
        current_target: "5 repos still need analysis work",
        progress_percent: null,
        primary_counts_label: "Processed in this Gemini refresh run",
        completed_count: 8,
        total_count: 8,
        remaining_count: 5,
        unit_label: "repos",
        secondary_counts_label: "Already analyzed across accepted repos",
        secondary_completed_count: 77,
        secondary_total_count: 84,
        secondary_remaining_count: 7,
        secondary_unit_label: "repos",
        updated_at: "2026-03-18T07:06:00Z",
        source: "analysis queue snapshot",
        details: ["Pending analysis: 5", "Repos currently marked in progress: 2", "Failed analyses awaiting retry: 1"],
      },
    },
  ],
};

const mockPauseStates = [
  {
    agent_name: "firehose",
    is_paused: true,
    paused_at: "2026-03-18T08:03:00Z",
    pause_reason: "Blocking failure in firehose",
    resume_condition: "Operator review required",
    triggered_by_event_id: 91,
    resumed_at: null,
    resumed_by: null,
  },
];

const mockFailureEvents = [
  {
    id: 91,
    event_type: "agent_failed",
    agent_name: "firehose",
    severity: "error",
    message: "firehose encountered an unexpected runtime failure.",
    context_json: null,
    agent_run_id: 11,
    created_at: "2026-03-18T08:03:00Z",
    failure_classification: "blocking",
    failure_severity: "error",
    http_status_code: null,
    retry_after_seconds: null,
    affected_repository_id: null,
    upstream_provider: "github",
  },
];

const mockSystemEvents = [
  {
    id: 201,
    event_type: "agent_paused",
    agent_name: "firehose",
    severity: "error",
    message: "firehose paused after failure",
    context_json: null,
    agent_run_id: 11,
    created_at: "2026-03-18T08:03:00Z",
  },
];

const mockGatewayRuntime = {
  contract_version: "test",
  availability: "available",
  runtime: {
    source_of_truth: "agentic-workflow",
    runtime_mode: "multi-agent",
    gateway_url: null,
    connection_state: "reserved",
    status: "unknown",
    route_owner: "agentic-workflow",
    agent_states: [
      {
        agent_key: "firehose",
        display_name: "Firehose",
        agent_role: "repository-intake-firehose",
        lifecycle_state: "planned",
        mvp_scope: "initial",
        queue: {
          status: "live",
          source_of_truth: "agentic-workflow",
          pending_items: 14,
          total_items: 120,
          state_counts: { pending: 14, in_progress: 2, completed: 104, failed: 0 },
          checkpoint: {
            kind: "firehose",
            next_page: 4,
            last_checkpointed_at: "2026-03-18T08:03:00Z",
            mirror_snapshot_generated_at: null,
            active_mode: "new",
            resume_required: false,
            new_anchor_date: "2026-03-18",
            trending_anchor_date: null,
            run_started_at: "2026-03-18T08:00:00Z",
          },
          notes: [],
        },
        monitoring: { status: "reserved", last_heartbeat_at: null, notes: [] },
        session_affinity: { source_of_truth: "gateway", session_id: null, route_key: null, status: "reserved" },
        notes: [],
      },
      {
        agent_key: "analyst",
        display_name: "Analyst",
        agent_role: "repository-analysis",
        lifecycle_state: "planned",
        mvp_scope: "initial",
        queue: { status: "reserved", pending_items: null, notes: [] },
        monitoring: { status: "reserved", last_heartbeat_at: null, notes: [] },
        session_affinity: { source_of_truth: "gateway", session_id: null, route_key: null, status: "reserved" },
        notes: [],
      },
    ],
    github_api_budget: null,
    gemini_api_key_pool: null,
    notes: [],
  },
};

const mockSettingsSummary = {
  project_settings: [],
  worker_settings: [{ key: "workers.FIREHOSE_INTERVAL_SECONDS", value: "300", source: "env", masked: false }],
};

const mockOverlord = {
  status: "Watching",
  headline: "Overlord monitoring",
  summary: "Watching pauses and queue pressure.",
  incidents: [],
  operator_todos: [],
};

vi.mock("@/api/overview", () => ({
  fetchOverviewSummary: vi.fn(() => Promise.resolve(mockOverviewSummary)),
  getOverviewSummaryQueryKey: vi.fn(() => ["overview", "summary"]),
}));

vi.mock("@/api/overlord", () => ({
  fetchOverlordSummary: vi.fn(() => Promise.resolve(mockOverlord)),
  getOverlordSummaryQueryKey: vi.fn(() => ["overlord", "summary"]),
}));

vi.mock("@/api/readiness", () => ({
  fetchGatewayRuntime: vi.fn(() => Promise.resolve(mockGatewayRuntime)),
  fetchSettingsSummary: vi.fn(() => Promise.resolve(mockSettingsSummary)),
}));

vi.mock("@/api/agents", () => ({
  AGENT_DISPLAY_ORDER: ["overlord", "firehose", "backfill", "bouncer", "analyst", "combiner", "obsession"],
  fetchLatestAgentRuns: vi.fn(() => Promise.resolve(mockLatestRuns)),
  fetchAgentPauseStates: vi.fn(() => Promise.resolve(mockPauseStates)),
  fetchFailureEvents: vi.fn(() => Promise.resolve(mockFailureEvents)),
  fetchSystemEvents: vi.fn(() => Promise.resolve(mockSystemEvents)),
  getLatestAgentRunsQueryKey: vi.fn(() => ["agents", "latest"]),
  getAgentPauseStatesQueryKey: vi.fn(() => ["agents", "pause"]),
  getFailureEventsQueryKey: vi.fn(() => ["agents", "failures"]),
  getSystemEventsQueryKey: vi.fn(() => ["agents", "events"]),
  sortAgentStatusEntries: vi.fn((entries) => entries),
}));

vi.mock("@/hooks/useEventStream", () => ({
  useEventStream: vi.fn(() => ({ connectionState: "open" })),
}));

vi.mock("@/components/agents/EventTimeline", () => ({
  EventTimeline: () => <div>Event timeline</div>,
}));

vi.mock("@/components/agents/GitHubBudgetPanel", () => ({
  GitHubBudgetPanel: () => <div>GitHub budget panel</div>,
}));

vi.mock("@/components/agents/GeminiKeyPoolPanel", () => ({
  GeminiKeyPoolPanel: () => <div>Gemini key panel</div>,
}));

vi.mock("@/components/dashboard/StatusBar", () => ({
  StatusBar: ({
    runningCount,
    readyCount,
    totalAgents,
  }: {
    runningCount: number;
    readyCount: number;
    totalAgents: number;
  }) => <div>{`Status bar ${runningCount}/${totalAgents} ${readyCount} idle`}</div>,
}));

vi.mock("@/components/dashboard/PipelineStrip", () => ({
  PipelineStrip: () => <div>Pipeline strip</div>,
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <OverviewPage />
    </QueryClientProvider>,
  );
}

describe("OverviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("explains paused agents in operator language directly on the overview", async () => {
    renderPage();

    expect(await screen.findByText("Attention Required")).toBeInTheDocument();
    expect(screen.getAllByText("Manual resume").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Next Run").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Remaining").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Failed and paused").length).toBeGreaterThan(0);
    expect(screen.getByText("Review pause reason, then resume from Control.")).toBeInTheDocument();
  });

  it("shows the workboard facts for schedule clarity and remaining workload", async () => {
    renderPage();

    expect(await screen.findByText("Fleet Workboard")).toBeInTheDocument();
    expect(screen.getAllByText("Status").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Idle backlog").length).toBeGreaterThan(0);
    expect(screen.getAllByText("8 repos").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Show details").length).toBeGreaterThan(0);
  });

  it("uses auto-retry language for retryable failures that are not paused", async () => {
    const originalPauseStates = mockPauseStates.splice(0, mockPauseStates.length);
    const originalFailureEvent = { ...mockFailureEvents[0] };

    mockFailureEvents[0] = {
      ...mockFailureEvents[0],
      event_type: "repository_discovery_failed",
      message: "firehose failed while discovering repositories from GitHub.",
      failure_classification: "retryable",
    };

    try {
      renderPage();

      expect(await screen.findByText("Attention Required")).toBeInTheDocument();
      expect(screen.getAllByText("Auto retry").length).toBeGreaterThan(0);
      expect(screen.getByText(/Automatic retry expected/)).toBeInTheDocument();
      expect(screen.getAllByText("Retryable failure").length).toBeGreaterThan(0);
    } finally {
      mockPauseStates.splice(0, mockPauseStates.length, ...originalPauseStates);
      mockFailureEvents[0] = originalFailureEvent;
    }
  });

  it("shows auto-resumed recovery language when automation already cleared the pause", async () => {
    const originalPauseState = { ...mockPauseStates[0] };

    mockPauseStates[0] = {
      ...mockPauseStates[0],
      is_paused: false,
      resumed_at: "2026-03-18T08:05:00Z",
      resumed_by: "auto",
      triggered_by_event_id: null,
    };

    try {
      renderPage();

      expect(await screen.findByText("Attention Required")).toBeInTheDocument();
      expect(screen.getAllByText("Auto-resumed").length).toBeGreaterThan(0);
      expect(
        screen.getAllByText((content) => content.includes("Automation cleared the previous protective pause")).length,
      ).toBeGreaterThan(0);
      expect(
        screen.getAllByText((content) => content.includes("This agent is back on its normal automatic scheduling")).length,
      ).toBeGreaterThan(0);
    } finally {
      mockPauseStates[0] = originalPauseState;
    }
  });

  it("keeps paused agents visible when latest-runs data is temporarily empty", async () => {
    const originalAgents = mockLatestRuns.agents.splice(0, mockLatestRuns.agents.length);

    try {
      renderPage();

      expect(await screen.findByText("Attention Required")).toBeInTheDocument();
      expect(screen.getByText("Status bar 0/7 6 idle")).toBeInTheDocument();
      expect(screen.queryByText("No idle agents.")).not.toBeInTheDocument();
      expect(screen.queryByText("No agents need attention right now.")).not.toBeInTheDocument();
      expect(screen.getAllByText("Firehose").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Repository intake").length).toBeGreaterThan(0);
    } finally {
      mockLatestRuns.agents.splice(0, mockLatestRuns.agents.length, ...originalAgents);
    }
  });
});

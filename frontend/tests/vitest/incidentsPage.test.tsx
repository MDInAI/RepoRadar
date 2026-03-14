import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import IncidentsClient from "@/app/incidents/IncidentsClient";

const mockIncidents = [
  {
    id: 1,
    event_type: "agent.failure",
    agent_name: "firehose",
    severity: "critical" as const,
    message: "Rate limit exceeded",
    created_at: "2026-03-11T10:00:00Z",
    failure_classification: "rate_limited" as const,
    failure_severity: "critical" as const,
    http_status_code: 429,
    retry_after_seconds: 3600,
    upstream_provider: "github",
    agent_run_id: 1,
    run_status: "failed" as const,
    run_started_at: "2026-03-11T09:55:00Z",
    run_completed_at: "2026-03-11T10:00:00Z",
    run_duration_seconds: 300,
    run_error_summary: "GitHub rate limit",
    affected_repository_id: 123,
    repository_full_name: "test/repo",
    is_paused: true,
    pause_reason: "Rate limited",
    resume_condition: "Wait for rate limit window",
    checkpoint_context: { mode: "firehose", page: 5, anchor_date: "2026-03-10", window_start: null, window_end: null, resume_required: true },
    routing_context: { session_id: "reserved-session-firehose", route_key: "agent.firehose", agent_key: "firehose" },
    context: { full_name: "test/repo" },
    next_action: "Wait for rate limit to expire, then resume agent in Story 4.6",
  },
  {
    id: 2,
    event_type: "agent.warning",
    agent_name: "analyst",
    severity: "warning" as const,
    message: "Transient error",
    created_at: "2026-03-11T11:00:00Z",
    failure_classification: "retryable" as const,
    failure_severity: "warning" as const,
    http_status_code: null,
    retry_after_seconds: null,
    upstream_provider: null,
    agent_run_id: 2,
    run_status: "completed" as const,
    run_started_at: "2026-03-11T10:55:00Z",
    run_completed_at: "2026-03-11T11:00:00Z",
    run_duration_seconds: 300,
    run_error_summary: null,
    affected_repository_id: null,
    repository_full_name: null,
    is_paused: false,
    pause_reason: null,
    resume_condition: null,
    checkpoint_context: null,
    routing_context: null,
    context: null,
    next_action: "Monitor for recurrence; automatic retry will handle transient issues",
  },
];

vi.mock("@/api/incidents", () => ({
  fetchIncidents: vi.fn(() => Promise.resolve(mockIncidents)),
  getIncidentsQueryKey: vi.fn((params) => ["incidents", params]),
}));

describe("IncidentsClient", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  });

  it("renders severity summary", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <IncidentsClient />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Rate limit exceeded")).toBeInTheDocument();
    });
  });

  it("displays incident list", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <IncidentsClient />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Rate limit exceeded")).toBeInTheDocument();
      expect(screen.getByText("Transient error")).toBeInTheDocument();
    });
  });

  it("shows routing context in detail panel", async () => {
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <IncidentsClient />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Rate limit exceeded")).toBeInTheDocument();
    });

    const incident = screen.getByText("Rate limit exceeded");
    incident.click();

    await waitFor(() => {
      expect(container.textContent).toContain("Routing Context");
      expect(container.textContent).toContain("reserved-session-firehose");
    });
  });

  it("displays checkpoint context", async () => {
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <IncidentsClient />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Rate limit exceeded")).toBeInTheDocument();
    });

    const incident = screen.getByText("Rate limit exceeded");
    incident.click();

    await waitFor(() => {
      expect(container.textContent).toContain("Checkpoint Context");
      expect(container.textContent).toContain("firehose");
    });
  });

  it("shows empty state when no incidents", async () => {
    const { fetchIncidents } = await import("@/api/incidents");
    vi.mocked(fetchIncidents).mockResolvedValueOnce([]);

    render(
      <QueryClientProvider client={queryClient}>
        <IncidentsClient />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("No incidents found")).toBeInTheDocument();
    });
  });

  it("displays severity totals", async () => {
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <IncidentsClient />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(container.textContent).toContain("Critical");
      expect(container.textContent).toContain("Warning");
    });
  });

  it("handles error state", async () => {
    const { fetchIncidents } = await import("@/api/incidents");
    vi.mocked(fetchIncidents).mockRejectedValueOnce(new Error("API error"));

    render(
      <QueryClientProvider client={queryClient}>
        <IncidentsClient />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  it("filters by agent name", async () => {
    const { fetchIncidents, getIncidentsQueryKey } = await import("@/api/incidents");

    render(
      <QueryClientProvider client={queryClient}>
        <IncidentsClient />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Rate limit exceeded")).toBeInTheDocument();
    });

    const agentFilter = screen.getByRole("combobox", { name: /agent/i });
    agentFilter.focus();

    await waitFor(() => {
      expect(vi.mocked(fetchIncidents)).toHaveBeenCalled();
    });
  });

  it("filters by severity", async () => {
    const { fetchIncidents } = await import("@/api/incidents");

    render(
      <QueryClientProvider client={queryClient}>
        <IncidentsClient />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Rate limit exceeded")).toBeInTheDocument();
    });

    const severityFilter = screen.getByRole("combobox", { name: /severity/i });
    severityFilter.focus();

    await waitFor(() => {
      expect(vi.mocked(fetchIncidents)).toHaveBeenCalled();
    });
  });

  it("filters by classification", async () => {
    const { fetchIncidents } = await import("@/api/incidents");

    render(
      <QueryClientProvider client={queryClient}>
        <IncidentsClient />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Rate limit exceeded")).toBeInTheDocument();
    });

    const classificationFilter = screen.getByRole("combobox", { name: /classification/i });
    classificationFilter.focus();

    await waitFor(() => {
      expect(vi.mocked(fetchIncidents)).toHaveBeenCalled();
    });
  });
});

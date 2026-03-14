import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import AgentsClient from "@/app/agents/AgentsClient";

vi.mock("@/hooks/useEventStream", () => ({
  useEventStream: () => ({ connectionState: "open" }),
}));

const latestRunsResponse = {
  agents: [
    { agent_name: "overlord", has_run: false, latest_run: null },
    {
      agent_name: "firehose",
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
      },
    },
    { agent_name: "backfill", has_run: false, latest_run: null },
    {
      agent_name: "bouncer",
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
      },
    },
    { agent_name: "analyst", has_run: false, latest_run: null },
    { agent_name: "combiner", has_run: false, latest_run: null },
    { agent_name: "obsession", has_run: false, latest_run: null },
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
  },
];

const eventsResponse = [
  {
    id: 91,
    event_type: "agent_started",
    agent_name: "bouncer",
    severity: "info",
    message: "bouncer run started.",
    context_json: null,
    agent_run_id: 12,
    created_at: "2026-03-10T10:05:00Z",
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
    const url = typeof input === "string" ? input : input.toString();
    const body = url.includes("/agents/runs/latest")
      ? latestRunsResponse
      : url.includes("/agents/pause-state")
        ? pauseStatesResponse
        : url.includes("/api/v1/events?")
          ? eventsResponse
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

function renderClientWithPauseStateError() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/agents/pause-state")) {
      return new Response(JSON.stringify({ error: { message: "pause-state outage" } }), {
        status: 500,
        headers: {
          "Content-Type": "application/json",
        },
      });
    }

    const body = url.includes("/agents/runs/latest")
      ? latestRunsResponse
      : url.includes("/api/v1/events?")
        ? eventsResponse
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

function deferredResponse() {
  let resolve: ((value: Response) => void) | null = null;
  const promise = new Promise<Response>((innerResolve) => {
    resolve = innerResolve;
  });

  return {
    promise,
    resolve(body: unknown) {
      resolve?.(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        }),
      );
    },
  };
}

describe("AgentsClient", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://api.test";
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  test("renders one agent status card per named agent", async () => {
    renderClient();

    expect(await screen.findByText("Real-time operational status")).toBeTruthy();
    await waitFor(() => {
      expect(screen.getAllByTestId(/agent-status-card-/)).toHaveLength(7);
    });
  });

  test("renders status badges with the expected palette", async () => {
    renderClient();

    const firehoseCard = await screen.findByTestId("agent-status-card-firehose");
    const bouncerCard = await screen.findByTestId("agent-status-card-bouncer");

    expect(within(firehoseCard).getByText("Completed").className).toContain("bg-emerald-100");
    expect(within(bouncerCard).getByText("Running").className).toContain("bg-amber-100");
  });

  test("renders the run history table columns", async () => {
    renderClient();

    expect(await screen.findAllByText("Run History")).toHaveLength(1);
    expect(screen.getByRole("columnheader", { name: "Agent" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Started" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Duration" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Items" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Error Summary" })).toBeTruthy();
    expect(await screen.findByText("Recovered after backoff")).toBeTruthy();
  });

  test("renders pause badge and details for a paused agent", async () => {
    renderClient();

    const firehoseCard = await screen.findByTestId("agent-status-card-firehose");
    expect(within(firehoseCard).getByText("PAUSED")).toBeTruthy();
    expect(within(firehoseCard).getByText("GitHub rate limit exceeded")).toBeTruthy();
    expect(
      within(firehoseCard).getByText("Rate limit window expires at 2026-03-10T11:00:00Z"),
    ).toBeTruthy();
  });

  test("announces the SSE stream state through a live status region", async () => {
    renderClient();

    expect((await screen.findByRole("status")).textContent).toContain("open");
  });

  test("shows the agent status loading state before the latest-runs query resolves", async () => {
    const latestRunsDeferred = deferredResponse();
    const agentRunsDeferred = deferredResponse();
    const eventsDeferred = deferredResponse();
    const pauseStatesDeferred = deferredResponse();
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/agents/runs/latest")) {
        return latestRunsDeferred.promise;
      }
      if (url.includes("/api/v1/events?")) {
        return eventsDeferred.promise;
      }
      if (url.includes("/agents/pause-state")) {
        return pauseStatesDeferred.promise;
      }
      return agentRunsDeferred.promise;
    });

    render(
      <QueryClientProvider client={queryClient}>
        <AgentsClient />
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId("agent-status-loading")).toBeTruthy();

    latestRunsDeferred.resolve(latestRunsResponse);
    agentRunsDeferred.resolve(agentRunsResponse);
    eventsDeferred.resolve(eventsResponse);
    pauseStatesDeferred.resolve(pauseStatesResponse);

    await waitFor(() => {
      expect(screen.getAllByTestId(/agent-status-card-/)).toHaveLength(7);
    });
  });

  test("marks pause state as unknown when the pause-state query fails", async () => {
    renderClientWithPauseStateError();

    expect(
      await screen.findByText("Unable to load agent pause states — pause badges may be missing or outdated."),
    ).toBeTruthy();

    const firehoseCard = await screen.findByTestId("agent-status-card-firehose");
    expect(within(firehoseCard).getByText("PAUSE UNKNOWN")).toBeTruthy();
    expect(
      within(firehoseCard).getByText(
        "Unavailable while the pause-state API request is failing.",
      ),
    ).toBeTruthy();
  });

  test("shows structured event timeline skeletons while event data is loading", async () => {
    const latestRunsDeferred = deferredResponse();
    const agentRunsDeferred = deferredResponse();
    const eventsDeferred = deferredResponse();
    const pauseStatesDeferred = deferredResponse();
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/agents/runs/latest")) {
        return latestRunsDeferred.promise;
      }
      if (url.includes("/api/v1/events?")) {
        return eventsDeferred.promise;
      }
      if (url.includes("/agents/pause-state")) {
        return pauseStatesDeferred.promise;
      }
      return agentRunsDeferred.promise;
    });

    render(
      <QueryClientProvider client={queryClient}>
        <AgentsClient />
      </QueryClientProvider>,
    );

    expect(await screen.findAllByTestId("event-timeline-skeleton")).toHaveLength(3);

    latestRunsDeferred.resolve(latestRunsResponse);
    agentRunsDeferred.resolve(agentRunsResponse);
    eventsDeferred.resolve(eventsResponse);
    pauseStatesDeferred.resolve(pauseStatesResponse);

    await waitFor(() => {
      expect(screen.getByText("bouncer run started.")).toBeTruthy();
    });
  });
});

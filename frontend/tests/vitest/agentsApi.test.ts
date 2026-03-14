import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import {
  AgentRequestError,
  fetchAgentRunDetail,
  fetchAgentRuns,
  fetchLatestAgentRuns,
  fetchSystemEvents,
} from "@/api/agents";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
    },
  });
}

describe("agents api runtime validation", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://api.test";
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("sorts the latest-runs response after validating its shape", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        agents: [
          { agent_name: "obsession", has_run: false, latest_run: null },
          { agent_name: "firehose", has_run: false, latest_run: null },
        ],
      }),
    );

    await expect(fetchLatestAgentRuns()).resolves.toEqual({
      agents: [
        { agent_name: "firehose", has_run: false, latest_run: null },
        { agent_name: "obsession", has_run: false, latest_run: null },
      ],
    });
  });

  test("rejects invalid latest-runs payloads", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        agents: [{ agent_name: "unknown-agent", has_run: false, latest_run: null }],
      }),
    );

    await expect(fetchLatestAgentRuns()).rejects.toMatchObject<Partial<AgentRequestError>>({
      code: "latest_runs_shape_invalid",
      message: "Latest agent runs response has unexpected shape",
    });
  });

  test("rejects invalid run-list payloads", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse([
        {
          id: 1,
          agent_name: "firehose",
          status: "mystery",
          started_at: "2026-03-10T10:00:00Z",
          completed_at: null,
          duration_seconds: null,
          items_processed: null,
          items_succeeded: null,
          items_failed: null,
          error_summary: null,
        },
      ]),
    );

    await expect(fetchAgentRuns()).rejects.toMatchObject<Partial<AgentRequestError>>({
      code: "agent_runs_shape_invalid",
    });
  });

  test("rejects invalid run-detail payloads", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        id: 1,
        agent_name: "firehose",
        status: "completed",
        started_at: "2026-03-10T10:00:00Z",
        completed_at: "2026-03-10T10:05:00Z",
        duration_seconds: 300,
        items_processed: 3,
        items_succeeded: 3,
        items_failed: 0,
        error_summary: null,
        error_context: null,
        events: [{ id: 7, event_type: "agent_started", agent_name: "firehose" }],
      }),
    );

    await expect(fetchAgentRunDetail(1)).rejects.toMatchObject<Partial<AgentRequestError>>({
      code: "agent_run_detail_shape_invalid",
    });
  });

  test("rejects invalid system-event payloads", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse([
        {
          id: 1,
          event_type: "agent_started",
          agent_name: "firehose",
          severity: "unknown",
          message: "started",
          context_json: null,
          agent_run_id: null,
          created_at: "2026-03-10T10:00:00Z",
        },
      ]),
    );

    await expect(fetchSystemEvents()).rejects.toMatchObject<Partial<AgentRequestError>>({
      code: "system_events_shape_invalid",
    });
  });

  test("rejects invalid agent run limits before issuing the request", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    await expect(fetchAgentRuns({ limit: 201 })).rejects.toMatchObject<
      Partial<AgentRequestError>
    >({
      code: "agent_runs_limit_invalid",
    });

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  test("rejects invalid system event limits before issuing the request", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    await expect(fetchSystemEvents({ limit: 0 })).rejects.toMatchObject<
      Partial<AgentRequestError>
    >({
      code: "system_events_limit_invalid",
    });

    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

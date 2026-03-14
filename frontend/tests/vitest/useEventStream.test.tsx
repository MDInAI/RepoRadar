import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { getLatestAgentRunsQueryKey, type AgentRunEvent } from "@/api/agents";
import { useEventStream } from "@/hooks/useEventStream";

class MockEventSource {
  static instances: MockEventSource[] = [];

  url: string;
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  listeners = new Map<string, EventListener[]>();
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(name: string, listener: EventListener) {
    const existing = this.listeners.get(name) ?? [];
    existing.push(listener);
    this.listeners.set(name, existing);
  }

  close() {
    this.closed = true;
  }

  emit(name: string, payload: unknown) {
    const event = {
      data: typeof payload === "string" ? payload : JSON.stringify(payload),
    } as MessageEvent<string>;

    for (const listener of this.listeners.get(name) ?? []) {
      listener(event as unknown as Event);
    }
  }

  static reset() {
    MockEventSource.instances = [];
  }
}

function HookHarness({
  onAgentRunUpdate,
}: {
  onAgentRunUpdate?: (payload: AgentRunEvent) => void;
}) {
  useEventStream({
    onAgentRunUpdate,
  });
  return null;
}

describe("useEventStream", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://api.test";
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
    MockEventSource.reset();
    vi.useFakeTimers();
    vi.stubGlobal("EventSource", MockEventSource as unknown as typeof EventSource);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  test("connects to the backend SSE endpoint", () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <HookHarness />
      </QueryClientProvider>,
    );

    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0]?.url).toBe("http://api.test/api/v1/events/stream");
  });

  test("reconnects with exponential backoff after disconnects", async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <HookHarness />
      </QueryClientProvider>,
    );

    const firstSource = MockEventSource.instances[0]!;
    act(() => {
      firstSource.onerror?.(new Event("error"));
    });
    expect(firstSource.closed).toBe(true);

    await act(async () => {
      vi.advanceTimersByTime(2_000);
    });
    expect(MockEventSource.instances).toHaveLength(2);

    const secondSource = MockEventSource.instances[1]!;
    act(() => {
      secondSource.onerror?.(new Event("error"));
    });

    await act(async () => {
      vi.advanceTimersByTime(4_000);
    });
    expect(MockEventSource.instances).toHaveLength(3);
  });

  test("invalidates TanStack Query data when run updates arrive", () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const onAgentRunUpdate = vi.fn();

    render(
      <QueryClientProvider client={queryClient}>
        <HookHarness onAgentRunUpdate={onAgentRunUpdate} />
      </QueryClientProvider>,
    );

    const source = MockEventSource.instances[0]!;
    act(() => {
      source.onopen?.(new Event("open"));
      source.emit("agent.run_completed", {
        id: 42,
        agent_name: "firehose",
        status: "completed",
        started_at: "2026-03-10T10:00:00Z",
        completed_at: "2026-03-10T10:03:00Z",
        duration_seconds: 180,
        items_processed: 4,
        items_succeeded: 4,
        items_failed: 0,
        error_summary: null,
      });
    });

    expect(onAgentRunUpdate).toHaveBeenCalledWith(expect.objectContaining({ id: 42 }));
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: getLatestAgentRunsQueryKey() }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["agents", "runs"] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["agents", "events"] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["overview", "summary"] }),
    );
  });

  test("invalidates pause-states query when agent_paused system event arrives", () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    render(
      <QueryClientProvider client={queryClient}>
        <HookHarness />
      </QueryClientProvider>,
    );

    const source = MockEventSource.instances[0]!;
    act(() => {
      source.onopen?.(new Event("open"));
      source.emit("system.event", {
        id: 101,
        event_type: "agent_paused",
        agent_name: "firehose",
        severity: "critical",
        message: "firehose paused due to GitHub rate limit.",
        context_json: null,
        agent_run_id: null,
        created_at: "2026-03-10T10:00:00Z",
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["agents", "events"] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["agents", "pause-states"] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["incidents"] }),
    );
  });

  test("pauses while the document is hidden and reconnects when visible again", async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <HookHarness />
      </QueryClientProvider>,
    );

    const source = MockEventSource.instances[0]!;

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });

    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });

    expect(source.closed).toBe(true);
    expect(MockEventSource.instances).toHaveLength(1);

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });

    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });

    expect(MockEventSource.instances).toHaveLength(2);
  });
});

/**
 * Unit tests for readiness fetch layer: timeout behavior and runtime shape validation.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReadinessRequestError, fetchGatewayContract, fetchGatewayRuntime } from "@/api/readiness";

vi.mock("@/api/base-url", () => ({
  getRequiredApiBaseUrl: () => "http://localhost:4101",
}));

function makeAbortingFetch() {
  return vi.fn().mockImplementation((_url: string, options?: RequestInit) => {
    return new Promise<Response>((_resolve, reject) => {
      options?.signal?.addEventListener("abort", () => {
        const err = new Error("The user aborted a request.");
        err.name = "AbortError";
        reject(err);
      });
    });
  });
}

describe("fetchReadinessSurface timeout", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("throws ReadinessRequestError with code request_timeout when fetch exceeds 10 s", async () => {
    vi.stubGlobal("fetch", makeAbortingFetch());

    const fetchPromise = fetchGatewayContract();

    // Attach rejection handler BEFORE advancing timers to avoid unhandled-rejection warning.
    const assertion = expect(fetchPromise).rejects.toSatisfy((err: unknown) => {
      return (
        err instanceof ReadinessRequestError &&
        err.code === "request_timeout" &&
        err.status === 0
      );
    });

    // Advance past the 10-second abort threshold.
    await vi.advanceTimersByTimeAsync(10_001);

    await assertion;
  });

  it("does not time out when the request completes within 10 s", async () => {
    const contract = {
      contract_version: "1.0.0",
      runtime_mode: "multi-agent",
      named_agents: [],
      architecture_flow: "frontend -> backend -> gateway",
      authority_boundary: [],
      frontend_boundary: { flow: "", direct_browser_gateway_access: false, notes: [] },
      canonical_interfaces: [],
      transport_target: {
        configured: true,
        url: null,
        scheme: null,
        allow_insecure_tls: false,
        token_configured: false,
        source: "test",
        notes: [],
      },
      dependency_chain: [],
      constraints: [],
      event_envelope: { version: "v1", channel: "test", delivery: "test", fields: [], notes: [] },
    };

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(contract),
      }),
    );

    await expect(fetchGatewayContract()).resolves.toMatchObject({
      contract_version: "1.0.0",
      runtime_mode: "multi-agent",
    });
  });

  it("throws ReadinessRequestError with code runtime_shape_invalid when runtime shape is wrong", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ unexpected: "shape" }),
      }),
    );

    await expect(fetchGatewayRuntime()).rejects.toSatisfy((err: unknown) => {
      return err instanceof ReadinessRequestError && err.code === "runtime_shape_invalid";
    });
  });

  it("throws ReadinessRequestError with code contract_shape_invalid when contract shape is wrong", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ unexpected: "shape" }),
      }),
    );

    await expect(fetchGatewayContract()).rejects.toSatisfy((err: unknown) => {
      return err instanceof ReadinessRequestError && err.code === "contract_shape_invalid";
    });
  });
});

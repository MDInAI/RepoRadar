import { fetchGatewayRuntime, ReadinessRequestError } from "@/api/readiness";
import type { GatewayRuntimeSurfaceResponse } from "@/lib/gateway-contract";

import { OverviewRuntimeClient } from "./OverviewRuntimeClient";

export default async function OverviewPage() {
  let runtime: GatewayRuntimeSurfaceResponse | null = null;
  let errorMessage: string | null = null;
  let initialUpdatedAt: string | null = null;

  try {
    runtime = await fetchGatewayRuntime();
    initialUpdatedAt = new Date().toISOString();
  } catch (error) {
    errorMessage =
      error instanceof ReadinessRequestError
        ? error.message
        : "Unable to load backend-owned intake status.";
  }

  return (
    <OverviewRuntimeClient
      initialRuntime={runtime}
      initialError={errorMessage}
      initialUpdatedAt={initialUpdatedAt}
    />
  );
}

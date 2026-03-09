import {
  type ConfigurationValidationIssue,
  type SettingsSummaryResponse,
  settingsContractEndpoints,
} from "@/lib/settings-contract";
import {
  type GatewayContractResponse,
  type GatewayRuntimeSurfaceResponse,
  gatewayContractEndpoints,
  isGatewayContractResponse,
  isGatewayRuntimeSurfaceResponse,
} from "@/lib/gateway-contract";
import { getRequiredApiBaseUrl } from "./base-url";

const FETCH_TIMEOUT_MS = 10_000;

function getApiBaseUrl(): string {
  return getRequiredApiBaseUrl();
}

interface ReadinessErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: {
      validation?: {
        issues?: ConfigurationValidationIssue[];
      };
    };
  };
}

function isReadinessErrorEnvelope(payload: unknown): payload is ReadinessErrorEnvelope {
  return (
    typeof payload === "object" &&
    payload !== null &&
    typeof (payload as ReadinessErrorEnvelope).error?.code === "string"
  );
}

export class ReadinessRequestError extends Error {
  status: number;
  code: string | null;
  validationIssues: ConfigurationValidationIssue[];

  constructor(
    message: string,
    options: {
      status: number;
      code?: string | null;
      validationIssues?: ConfigurationValidationIssue[];
    },
  ) {
    super(message);
    this.name = "ReadinessRequestError";
    this.status = options.status;
    this.code = options.code ?? null;
    this.validationIssues = options.validationIssues ?? [];
  }
}

async function fetchReadinessSurface<T>(
  path: string,
  surfaceLabel: string,
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  try {
    const res = await fetch(`${getApiBaseUrl()}${path}`, {
      // Treat readiness data as dynamic so drift is visible immediately.
      cache: "no-store",
      signal: controller.signal,
    });

    if (res.ok) {
      return res.json() as Promise<T>;
    }

    let payload: ReadinessErrorEnvelope | null = null;
    try {
      const raw: unknown = await res.json();
      payload = isReadinessErrorEnvelope(raw) ? raw : null;
    } catch {
      payload = null;
    }

    const message =
      payload?.error?.message ||
      `Failed to fetch ${surfaceLabel}: ${res.status} ${res.statusText}`.trim();

    throw new ReadinessRequestError(message, {
      status: res.status,
      code: payload?.error?.code,
      validationIssues: payload?.error?.details?.validation?.issues ?? [],
    });
  } catch (err) {
    if (err instanceof ReadinessRequestError) throw err;
    if (err instanceof Error && err.name === "AbortError") {
      throw new ReadinessRequestError(`Request timed out fetching ${surfaceLabel}`, {
        status: 0,
        code: "request_timeout",
      });
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchSettingsSummary(): Promise<SettingsSummaryResponse> {
  return fetchReadinessSurface<SettingsSummaryResponse>(
    settingsContractEndpoints.summary,
    "settings summary",
  );
}

export async function fetchGatewayContract(): Promise<GatewayContractResponse> {
  const data = await fetchReadinessSurface<unknown>(
    gatewayContractEndpoints.contract,
    "gateway contract",
  );
  if (!isGatewayContractResponse(data)) {
    throw new ReadinessRequestError("Gateway contract response has unexpected shape", {
      status: 0,
      code: "contract_shape_invalid",
    });
  }
  return data;
}

export async function fetchGatewayRuntime(): Promise<GatewayRuntimeSurfaceResponse> {
  const data = await fetchReadinessSurface<unknown>(
    gatewayContractEndpoints.runtime,
    "gateway runtime",
  );
  if (!isGatewayRuntimeSurfaceResponse(data)) {
    throw new ReadinessRequestError("Gateway runtime response has unexpected shape", {
      status: 0,
      code: "runtime_shape_invalid",
    });
  }
  return data;
}

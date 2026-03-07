import {
  type ConfigurationValidationIssue,
  type SettingsSummaryResponse,
  settingsContractEndpoints,
} from "@/lib/settings-contract";
import {
  type GatewayContractResponse,
  type GatewayRuntimeSurfaceResponse,
  gatewayContractEndpoints,
} from "@/lib/gateway-contract";

function getApiBaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) {
    throw new Error("NEXT_PUBLIC_API_URL is required but not configured.");
  }
  return url;
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
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    // Treat readiness data as dynamic so drift is visible immediately.
    cache: "no-store",
  });

  if (res.ok) {
    return res.json();
  }

  let payload: ReadinessErrorEnvelope | null = null;
  try {
    payload = (await res.json()) as ReadinessErrorEnvelope;
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
}

export async function fetchSettingsSummary(): Promise<SettingsSummaryResponse> {
  return fetchReadinessSurface<SettingsSummaryResponse>(
    settingsContractEndpoints.summary,
    "settings summary",
  );
}

export async function fetchGatewayContract(): Promise<GatewayContractResponse> {
  return fetchReadinessSurface<GatewayContractResponse>(
    gatewayContractEndpoints.contract,
    "gateway contract",
  );
}

export async function fetchGatewayRuntime(): Promise<GatewayRuntimeSurfaceResponse> {
  return fetchReadinessSurface<GatewayRuntimeSurfaceResponse>(
    gatewayContractEndpoints.runtime,
    "gateway runtime",
  );
}

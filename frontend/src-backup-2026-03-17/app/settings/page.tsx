import {
  ReadinessRequestError,
  fetchSettingsSummary,
  fetchGatewayContract,
  fetchGatewayRuntime,
} from "@/api/readiness";
import type { GatewayContractResponse, GatewayRuntimeSurfaceResponse } from "@/lib/gateway-contract";
import type {
  ConfigurationValidationIssue,
  MaskedSettingSummary,
  SettingsSummaryResponse,
} from "@/lib/settings-contract";

// Force dynamic rendering since we are reading configuration that can drift
export const dynamic = "force-dynamic";

type ReadinessSurfaceError = {
  surface: string;
  message: string;
  code: string | null;
  status: number | null;
  validationIssues: ConfigurationValidationIssue[];
};

type ReadinessSection = {
  title: string;
  description: string;
  emptyMessage: string;
  settings: MaskedSettingSummary[];
};

function dedupeIssues(
  issues: ConfigurationValidationIssue[],
): ConfigurationValidationIssue[] {
  const seen = new Set<string>();

  return issues.filter((issue) => {
    const key = [
      issue.severity,
      issue.field,
      issue.owner,
      issue.code,
      issue.message,
      issue.source,
    ].join("|");

    if (seen.has(key)) {
      return false;
    }

    seen.add(key);
    return true;
  });
}

function normalizeError(
  surface: string,
  reason: unknown,
): ReadinessSurfaceError {
  if (reason instanceof ReadinessRequestError) {
    return {
      surface,
      message: reason.message,
      code: reason.code,
      status: reason.status,
      validationIssues: reason.validationIssues,
    };
  }

  if (reason instanceof Error) {
    return {
      surface,
      message: reason.message,
      code: null,
      status: null,
      validationIssues: [],
    };
  }

  return {
    surface,
    message: `Failed to load ${surface}.`,
    code: null,
    status: null,
    validationIssues: [],
  };
}

function formatGatewayConnectionState(
  gatewayContract: GatewayContractResponse | null,
  gatewayRuntime: GatewayRuntimeSurfaceResponse | null,
) {
  if (gatewayRuntime?.runtime.connection_state === "reserved") {
    return {
      label: "Reserved placeholder",
      dotClassName: "bg-amber-500",
      note: "Live Gateway connectivity checks land in later runtime stories.",
    };
  }

  if (gatewayContract?.transport_target.configured === false) {
    return {
      label: "Not configured",
      dotClassName: "bg-red-500",
      note: "Gateway transport details are missing from the backend-owned config summary.",
    };
  }

  return {
    label: "Unknown",
    dotClassName: "bg-neutral-500",
    note: "Gateway runtime availability could not be confirmed from the current backend response.",
  };
}

function buildSections(
  settingsSummary: SettingsSummaryResponse | null,
): ReadinessSection[] {
  const projectRuntimeSettings =
    settingsSummary?.project_settings.filter(
      (setting) => setting.owner === "agentic-workflow",
    ) ?? [];

  const workspaceContextSettings =
    settingsSummary?.worker_settings.filter(
      (setting) => setting.owner === "workspace",
    ) ?? [];

  const workerRuntimeSettings =
    settingsSummary?.worker_settings.filter(
      (setting) => setting.owner === "agentic-workflow",
    ) ?? [];
  const openclawReferenceSettings =
    settingsSummary?.project_settings.filter(
      (setting) => setting.owner === "openclaw",
    ) ?? [];

  return [
    {
      title: "Project Runtime",
      description: "Local app-owned config and credentials",
      emptyMessage: "No project runtime settings found.",
      settings: projectRuntimeSettings,
    },
    {
      title: "Workspace Context",
      description: "Worker-side local context and drift visibility",
      emptyMessage: "No worker workspace settings found.",
      settings: workspaceContextSettings,
    },
    {
      title: "Worker Runtime",
      description: "Worker-side app-owned config and credentials",
      emptyMessage: "No worker runtime settings found.",
      settings: workerRuntimeSettings,
    },
    {
      title: "OpenClaw References",
      description: "OpenClaw-owned config references exposed by the backend",
      emptyMessage: "No OpenClaw reference settings found.",
      settings: [...(settingsSummary?.openclaw_settings ?? []), ...openclawReferenceSettings],
    },
  ];
}

export default async function SettingsPage() {
  let settingsSummary: SettingsSummaryResponse | null = null;
  let gatewayContract: GatewayContractResponse | null = null;
  let gatewayRuntime: GatewayRuntimeSurfaceResponse | null = null;

  const surfaceResults = await Promise.allSettled([
    fetchSettingsSummary(),
    fetchGatewayContract(),
    fetchGatewayRuntime(),
  ]);

  const surfaceErrors: ReadinessSurfaceError[] = [];

  const [summaryResult, contractResult, runtimeResult] = surfaceResults;

  if (summaryResult.status === "fulfilled") {
    settingsSummary = summaryResult.value;
  } else {
    surfaceErrors.push(normalizeError("settings summary", summaryResult.reason));
  }

  if (contractResult.status === "fulfilled") {
    gatewayContract = contractResult.value;
  } else {
    surfaceErrors.push(normalizeError("gateway contract", contractResult.reason));
  }

  if (runtimeResult.status === "fulfilled") {
    gatewayRuntime = runtimeResult.value;
  } else {
    surfaceErrors.push(normalizeError("gateway runtime", runtimeResult.reason));
  }

  const validationIssues = dedupeIssues([
    ...(settingsSummary?.validation.issues ?? []),
    ...surfaceErrors.flatMap((error) => error.validationIssues),
  ]);
  const blockingIssues = validationIssues.filter((issue) => issue.severity === "error");
  const warningIssues = validationIssues.filter((issue) => issue.severity === "warning");
  const transportErrors = surfaceErrors.filter(
    (error) => error.validationIssues.length === 0,
  );
  const isReady = transportErrors.length === 0 && blockingIssues.length === 0;
  const gatewayState = formatGatewayConnectionState(gatewayContract, gatewayRuntime);
  const sections = buildSections(settingsSummary);

  return (
    <main className="space-y-8 p-8 max-w-5xl">
      <header className="space-y-2 pb-6 border-b border-neutral-800">
        <h1 className="text-3xl font-bold tracking-tight text-neutral-100">System Readiness</h1>
        <p className="text-neutral-400 text-lg">
          Workspace prerequisites, Gateway connectivity, and Project Runtime validation.
        </p>
      </header>

      {transportErrors.length > 0 && validationIssues.length === 0 ? (
        <section className="rounded-xl border border-red-500/50 bg-red-500/10 p-5 text-red-400">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" role="img" aria-label="Alert icon"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>
            Readiness Surface Unavailable
          </h2>
          <p className="mt-2 text-sm text-red-400/80">
            One or more backend-owned readiness surfaces could not be loaded.
          </p>
          <ul className="mt-3 space-y-2 text-sm text-red-300/90">
            {transportErrors.map((error) => (
              <li key={`${error.surface}:${error.message}`}>
                <span className="font-semibold">{error.surface}:</span> {error.message}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {transportErrors.length === 0 && (
        <section className={`rounded-xl border p-5 flex items-start gap-4 ${isReady ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-400" : "border-amber-500/50 bg-amber-500/10 text-amber-400"}`}>
          <div className={`mt-0.5 p-2 rounded-full ${isReady ? "bg-emerald-500/20" : "bg-amber-500/20"}`}>
            <div className={`w-3 h-3 rounded-full ${isReady ? "bg-emerald-500" : "bg-amber-500"}`} />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-neutral-100">
              {isReady ? "Ready for Intake" : "Setup Issues Detected"}
            </h2>
            <p className="text-sm mt-1 mb-2">
              {isReady
                ? warningIssues.length > 0
                  ? `No blocking issues remain. ${warningIssues.length} warning(s) still need attention.`
                  : "All required prerequisites are valid. The project is ready to process repositories."
                : `${blockingIssues.length} blocking error(s) and ${warningIssues.length} warning(s) need attention.`}
            </p>
            {warningIssues.length > 0 && (
              <p className="text-sm text-amber-500/80">
                Warnings detected, but the system is functional. You can proceed with caution.
              </p>
            )}
          </div>
        </section>
      )}

      <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Gateway Connectivity Card */}
        <article className="rounded-xl border border-neutral-800 bg-neutral-900 overflow-hidden flex flex-col lg:col-span-1">
          <div className="border-b border-neutral-800 bg-neutral-900/50 px-5 py-4">
            <h3 className="font-semibold text-neutral-200">Gateway Transport</h3>
            <p className="text-xs text-neutral-500 mt-1">Connectivity & backend authority</p>
          </div>
          <div className="p-5 flex-1 space-y-4">
            <div className="space-y-1">
              <div className="text-xs text-neutral-500 uppercase tracking-wider font-semibold">Runtime Mode</div>
              <div className="font-mono text-sm px-2 py-0.5 bg-neutral-800 rounded inline-block text-neutral-300">
                {gatewayContract?.runtime_mode || "Unknown"}
              </div>
            </div>

            <div className="space-y-1">
              <div className="text-xs text-neutral-500 uppercase tracking-wider font-semibold">Target URL</div>
              <div className="text-sm text-neutral-300 break-all font-mono">
                {gatewayContract?.transport_target.url ||
                  gatewayRuntime?.runtime.gateway_url ||
                  "Not configured"}
              </div>
            </div>

            <div className="space-y-1">
              <div className="text-xs text-neutral-500 uppercase tracking-wider font-semibold">Connection State</div>
              <div className="text-sm flex items-center gap-2 text-neutral-300">
                <span className={`w-2 h-2 rounded-full ${gatewayState.dotClassName}`}></span>
                {gatewayState.label}
              </div>
              <p className="text-xs text-neutral-500">{gatewayState.note}</p>
            </div>
          </div>
        </article>

        {sections.map((section) => (
          <article
            key={section.title}
            className="rounded-xl border border-neutral-800 bg-neutral-900 overflow-hidden flex flex-col"
          >
            <div className="border-b border-neutral-800 bg-neutral-900/50 px-5 py-4">
              <h3 className="font-semibold text-neutral-200">{section.title}</h3>
              <p className="text-xs text-neutral-500 mt-1">{section.description}</p>
            </div>
            <div className="p-5 flex-1 space-y-3">
              {section.settings.length > 0 ? (
                section.settings.map((setting) => (
                  <div
                    key={`${section.title}:${setting.key}`}
                    className="flex justify-between items-center py-2 border-b border-neutral-800/50 last:border-0"
                  >
                    <div>
                      <div className="text-sm font-medium text-neutral-300">{setting.label}</div>
                      <div className="text-xs text-neutral-500 font-mono mt-0.5 truncate max-w-[170px]">
                        {setting.key}
                      </div>
                    </div>
                    <div>
                      {setting.configured ? (
                        <span className="text-xs font-semibold px-2 py-1 bg-emerald-500/10 text-emerald-400 rounded-md">
                          Configured
                        </span>
                      ) : (
                        <span className="text-xs font-semibold px-2 py-1 bg-amber-500/10 text-amber-400 rounded-md">
                          Missing
                        </span>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-sm text-neutral-500 italic">{section.emptyMessage}</div>
              )}
            </div>
          </article>
        ))}
      </section>

      {transportErrors.length > 0 && validationIssues.length > 0 ? (
        <section className="rounded-xl border border-red-500/30 bg-red-500/5 p-5">
          <h3 className="text-lg font-semibold text-neutral-200">Unavailable Readiness Surfaces</h3>
          <div className="mt-3 space-y-2 text-sm text-red-300/90">
            {transportErrors.map((error) => (
              <p key={`${error.surface}:${error.message}`}>
                <span className="font-semibold">{error.surface}:</span> {error.message}
              </p>
            ))}
          </div>
        </section>
      ) : null}

      {/* Validation Issues List */}
      {validationIssues.length > 0 && (
        <section className="space-y-4">
          <h3 className="text-lg font-semibold border-b border-neutral-800 pb-2 text-neutral-200">
            Validation Errors & Warnings
          </h3>
          <div className="grid gap-4">
            {validationIssues.map((issue, index) => (
              <article key={`${issue.code}:${issue.field}:${index}`} className={`rounded-xl border p-5 ${issue.severity === "error" ? "border-red-500/20 bg-red-500/5" : "border-amber-500/20 bg-amber-500/5"}`}>
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${issue.severity === "error" ? "bg-red-500/20 text-red-400" : "bg-amber-500/20 text-amber-400"}`}>
                        {issue.severity}
                      </span>
                      <span className="text-sm font-semibold text-neutral-200">{issue.code}</span>
                    </div>
                    <p className="text-neutral-300 mt-2 text-sm max-w-2xl">{issue.message}</p>
                  </div>
                  <div className="text-left sm:text-right shrink-0">
                    <span className="text-[10px] text-neutral-500 uppercase tracking-wider font-semibold block">
                      Owner Boundary
                    </span>
                    <div className="text-sm font-mono text-neutral-400 mt-1">{issue.owner}</div>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-4 text-xs text-neutral-400 font-mono bg-black/30 p-3 rounded-lg border border-white/5">
                  <div>
                    <span className="text-neutral-600 mr-2">Field:</span>
                    <span className="text-neutral-300">{issue.field}</span>
                  </div>
                  <div>
                    <span className="text-neutral-600 mr-2">Source:</span>
                    <span className="text-neutral-300">{issue.source}</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}

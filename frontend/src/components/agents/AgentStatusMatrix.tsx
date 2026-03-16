import Link from "next/link";

import {
  AGENT_DISPLAY_ORDER,
  sortAgentStatusEntries,
  type AgentName,
  type AgentPauseState,
  type AgentStatusEntry,
} from "@/api/agents";

import {
  formatAgentName,
  formatAgentRunStatus,
  formatItemsSummary,
  formatRelativeTimestamp,
  formatRuntimeProgressCounts,
  formatRuntimeProgressHeadline,
  getRunStatusBadgeClassName,
} from "./agentPresentation";
import { PauseAgentButton } from "./PauseAgentButton";
import { ResumeAgentButton } from "./ResumeAgentButton";

// Agents with runtime pause check implementations
const AGENTS_WITH_PAUSE_SUPPORT: AgentName[] = ["firehose", "backfill", "bouncer", "analyst"];

export function AgentStatusMatrix({
  agents,
  pauseStates = [],
  pauseStateStatus = "available",
  description,
  isLoading = false,
  title,
  variant = "detail",
}: {
  agents: AgentStatusEntry[];
  pauseStates?: AgentPauseState[];
  pauseStateStatus?: "available" | "unavailable" | "loading";
  description: string;
  isLoading?: boolean;
  title: string;
  variant?: "compact" | "detail";
}) {
  const orderedAgents = sortAgentStatusEntries(agents);
  const pauseMap = new Map(pauseStates.map((ps) => [ps.agent_name, ps]));
  const loadingCards = variant === "compact" ? AGENT_DISPLAY_ORDER : AGENT_DISPLAY_ORDER.slice(0, 6);

  const renderProgressBar = (percent: number | null | undefined) => {
    if (percent == null) {
      return null;
    }
    return (
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200">
        <div
          className="h-full rounded-full bg-orange-500 transition-[width]"
          style={{ width: `${Math.max(0, Math.min(percent, 100))}%` }}
        />
      </div>
    );
  };

  return (
    <section
      aria-busy={isLoading}
      className="rounded-[2rem] border border-black/10 bg-white/90 p-6 shadow-[0_24px_70px_-40px_rgba(15,23,42,0.55)]"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-orange-700">
            {title}
          </p>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">{description}</p>
          {isLoading ? (
            <p
              className="mt-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500"
              data-testid="agent-status-loading"
            >
              Loading the latest backend-derived agent status.
            </p>
          ) : null}
        </div>
        <Link
          className="inline-flex h-fit items-center justify-center rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
          href="/agents"
        >
          Open agents view
        </Link>
      </div>

      {isLoading && orderedAgents.length === 0 ? (
        variant === "compact" ? (
          <ul className="mt-5 grid gap-3">
            {loadingCards.map((agentName) => (
              <li key={agentName}>
                <div className="grid animate-pulse gap-3 rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-4 sm:grid-cols-[1.2fr_1fr_1fr]">
                  <div className="space-y-2">
                    <div className="h-4 w-28 rounded-full bg-slate-200" />
                    <div className="h-3 w-36 rounded-full bg-slate-100" />
                  </div>
                  <div className="flex items-center">
                    <div className="h-7 w-24 rounded-full bg-slate-200" />
                  </div>
                  <div className="flex items-center">
                    <div className="h-3 w-32 rounded-full bg-slate-100" />
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <ul className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {loadingCards.map((agentName) => (
              <li
                key={agentName}
                className="rounded-[1.8rem] border border-slate-200 bg-slate-50/70 p-5"
              >
                <div className="animate-pulse space-y-5">
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-2">
                      <div className="h-5 w-28 rounded-full bg-slate-200" />
                      <div className="h-3 w-32 rounded-full bg-slate-100" />
                    </div>
                    <div className="h-7 w-24 rounded-full bg-slate-200" />
                  </div>
                  <div className="space-y-4">
                    <div>
                      <div className="h-3 w-12 rounded-full bg-slate-100" />
                      <div className="mt-2 h-4 w-24 rounded-full bg-slate-200" />
                    </div>
                    <div>
                      <div className="h-3 w-24 rounded-full bg-slate-100" />
                      <div className="mt-2 h-4 w-36 rounded-full bg-slate-200" />
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )
      ) : variant === "compact" ? (
        <ul className="mt-5 grid gap-3">
          {orderedAgents.map((entry) => {
            const status = entry.latest_run?.status ?? "never_run";
            const pauseState = pauseMap.get(entry.agent_name);
            const isPaused = pauseState?.is_paused ?? false;
            const pauseStateUnavailable = pauseStateStatus === "unavailable";
            const pauseStateLoading = pauseStateStatus === "loading";
            return (
              <li key={entry.agent_name}>
                <Link
                  className="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-4 transition hover:border-orange-200 hover:bg-orange-50 sm:grid-cols-[1.2fr_1fr_1fr]"
                  href="/agents"
                >
                  <div>
                    <p className="text-sm font-semibold text-slate-950">
                      {formatAgentName(entry.agent_name)}
                    </p>
                    <p className="mt-1 text-sm text-slate-600">
                      {formatRuntimeProgressHeadline(entry.runtime_progress) || formatItemsSummary(entry.latest_run)}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {formatRuntimeProgressCounts(entry.runtime_progress)}
                    </p>
                    {renderProgressBar(entry.runtime_progress?.progress_percent)}
                  </div>
                  <div className="flex flex-col gap-1.5">
                    {pauseStateUnavailable ? (
                      <span className="inline-flex rounded-full border border-slate-300 bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-800">
                        PAUSE UNKNOWN
                      </span>
                    ) : null}
                    {pauseStateLoading ? (
                      <span className="inline-flex rounded-full border border-slate-300 bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-800">
                        PAUSE LOADING
                      </span>
                    ) : null}
                    {isPaused && !pauseStateUnavailable && !pauseStateLoading && (
                      <span className="inline-flex rounded-full border border-amber-300 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-900">
                        PAUSED
                      </span>
                    )}
                    <span
                      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${getRunStatusBadgeClassName(
                        status,
                      )}`}
                    >
                      {entry.latest_run ? formatAgentRunStatus(entry.latest_run.status) : "No runs"}
                    </span>
                  </div>
                  <div className="text-sm text-slate-600">
                    {entry.runtime_progress?.updated_at
                      ? `Live update ${formatRelativeTimestamp(entry.runtime_progress.updated_at)}`
                      : `Last activity ${formatRelativeTimestamp(entry.latest_run?.started_at ?? null)}`}
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : (
        <ul className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {orderedAgents.map((entry) => {
            const status = entry.latest_run?.status ?? "never_run";
            const pauseState = pauseMap.get(entry.agent_name);
            const isPaused = pauseStateStatus === "available" ? (pauseState?.is_paused ?? false) : false;
            const pauseStateUnavailable = pauseStateStatus === "unavailable";
            const pauseStateLoading = pauseStateStatus === "loading";
            return (
              <li
                key={entry.agent_name}
                className="rounded-[1.8rem] border border-slate-200 bg-slate-50/70 p-5"
                data-testid={`agent-status-card-${entry.agent_name}`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-lg font-semibold text-slate-950">
                      {formatAgentName(entry.agent_name)}
                    </p>
                    <p className="mt-1 text-sm text-slate-600">
                      Last activity {formatRelativeTimestamp(entry.latest_run?.started_at ?? null)}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1.5">
                    {pauseStateUnavailable ? (
                      <span className="inline-flex rounded-full border border-slate-300 bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-800">
                        PAUSE UNKNOWN
                      </span>
                    ) : null}
                    {pauseStateLoading ? (
                      <span className="inline-flex rounded-full border border-slate-300 bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-800">
                        PAUSE LOADING
                      </span>
                    ) : null}
                    {isPaused && !pauseStateUnavailable && !pauseStateLoading && (
                      <span className="inline-flex rounded-full border border-amber-300 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-900">
                        PAUSED
                      </span>
                    )}
                    <span
                      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${getRunStatusBadgeClassName(
                        status,
                      )}`}
                    >
                      {entry.latest_run ? formatAgentRunStatus(entry.latest_run.status) : "No runs"}
                    </span>
                  </div>
                </div>
                <dl className="mt-5 grid gap-3 text-sm text-slate-600">
                  {pauseStateUnavailable ? (
                    <div>
                      <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">
                        Pause state
                      </dt>
                      <dd className="mt-1 text-slate-900">
                        Unavailable while the pause-state API request is failing.
                      </dd>
                    </div>
                  ) : null}
                  {isPaused && !pauseStateUnavailable && (
                    <>
                      <div>
                        <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">
                          Pause reason
                        </dt>
                        <dd className="mt-1 text-slate-900">
                          {pauseState?.pause_reason ?? "Unknown"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">
                          Resume condition
                        </dt>
                        <dd className="mt-1 text-slate-900">
                          {pauseState?.resume_condition ?? "Unknown"}
                        </dd>
                      </div>
                      {AGENTS_WITH_PAUSE_SUPPORT.includes(entry.agent_name) && (
                        <div>
                          <ResumeAgentButton agentName={entry.agent_name} />
                        </div>
                      )}
                    </>
                  )}
                  {!isPaused && !pauseStateUnavailable && !pauseStateLoading && AGENTS_WITH_PAUSE_SUPPORT.includes(entry.agent_name) && (
                    <div>
                      <PauseAgentButton agentName={entry.agent_name} />
                    </div>
                  )}
                  <div>
                    <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Items</dt>
                    <dd className="mt-1 font-medium text-slate-900">
                      {formatItemsSummary(entry.latest_run)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      Live work
                    </dt>
                    <dd className="mt-1 text-slate-900">
                      {formatRuntimeProgressHeadline(entry.runtime_progress)}
                    </dd>
                    <div className="mt-1 text-xs text-slate-600">
                      {formatRuntimeProgressCounts(entry.runtime_progress)}
                    </div>
                    {renderProgressBar(entry.runtime_progress?.progress_percent)}
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      Error summary
                    </dt>
                    <dd className="mt-1 text-slate-700">
                      {entry.latest_run?.error_summary ?? "No active error context"}
                    </dd>
                  </div>
                  {entry.runtime_progress?.details?.length ? (
                    <div>
                      <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">
                        Runtime detail
                      </dt>
                      <dd className="mt-1 space-y-1 text-slate-700">
                        {entry.runtime_progress.details.slice(0, 2).map((detail) => (
                          <p key={detail}>{detail}</p>
                        ))}
                      </dd>
                    </div>
                  ) : null}
                </dl>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

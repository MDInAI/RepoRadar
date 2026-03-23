"use client";

import { useEffect, useRef, useState } from "react";

import type { SystemEventPayload } from "@/api/agents";

import {
  formatAgentName,
  formatSeverityLabel,
  formatTimestampLabel,
  getSeverityBadgeClassName,
} from "./agentPresentation";

export function EventTimeline({
  events,
  isLoading,
}: {
  events: SystemEventPayload[];
  isLoading: boolean;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true);
  const [pausedAtCount, setPausedAtCount] = useState(events.length);
  const pausedEventCount = autoScrollEnabled ? 0 : Math.max(events.length - pausedAtCount, 0);

  useEffect(() => {
    if (!containerRef.current || !autoScrollEnabled) {
      return;
    }
    containerRef.current.scrollTop = containerRef.current.scrollHeight;
  }, [autoScrollEnabled, events]);

  return (
    <section className="rounded-[2rem] border border-black/10 bg-white/90 p-5 shadow-[0_24px_70px_-40px_rgba(15,23,42,0.55)]">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-orange-700">
            Event Timeline
          </p>
          <p className="mt-2 text-sm text-slate-600">
            Recent backend events stream in here as workers persist operational updates.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {!autoScrollEnabled && pausedEventCount > 0 ? (
            <span className="rounded-full border border-orange-200 bg-orange-50 px-3 py-1 text-xs font-semibold text-orange-900">
              {pausedEventCount} new event{pausedEventCount === 1 ? "" : "s"}
            </span>
          ) : null}
          <button
            aria-pressed={!autoScrollEnabled}
            className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
            type="button"
            onClick={() => {
              if (autoScrollEnabled) {
                setPausedAtCount(events.length);
                setAutoScrollEnabled(false);
                return;
              }

              setPausedAtCount(events.length);
              setAutoScrollEnabled(true);
            }}
          >
            {autoScrollEnabled ? "Pause auto-scroll" : "Resume auto-scroll"}
          </button>
        </div>
      </div>

      <div
        className="mt-5 max-h-[34rem] space-y-3 overflow-y-auto pr-1"
        ref={containerRef}
      >
        {isLoading ? (
          Array.from({ length: 3 }, (_, index) => (
            <article
              key={index}
              className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-4"
              data-testid="event-timeline-skeleton"
            >
              <div className="animate-pulse space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="h-6 w-20 rounded-full bg-slate-200" />
                  <div className="h-3 w-24 rounded-full bg-slate-100" />
                </div>
                <div className="h-4 w-4/5 rounded-full bg-slate-200" />
                <div className="h-3 w-40 rounded-full bg-slate-100" />
              </div>
            </article>
          ))
        ) : null}

        {!isLoading && events.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
            No system events recorded yet.
          </div>
        ) : null}

        {events.map((event) => (
          <article
            key={event.id}
            className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-4"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${getSeverityBadgeClassName(
                  event.severity,
                )}`}
              >
                {formatSeverityLabel(event.severity)}
              </span>
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                {formatAgentName(event.agent_name)}
              </span>
            </div>
            <p className="mt-3 text-sm font-medium text-slate-900">{event.message}</p>
            <p className="mt-2 text-xs text-slate-500">
              {formatTimestampLabel(event.created_at)} · {event.event_type}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

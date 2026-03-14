"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useEffectEvent, useRef, useState } from "react";

import {
  getAgentRunDetailQueryKey,
  getEventStreamUrl,
  getLatestAgentRunsQueryKey,
  isAgentRunEvent,
  isSystemEventPayload,
  type AgentRunEvent,
  type SystemEventPayload,
} from "@/api/agents";

const INITIAL_RECONNECT_DELAY_MS = 2_000;
const MAX_RECONNECT_DELAY_MS = 30_000;

export type EventStreamConnectionState = "connecting" | "open" | "closed" | "error";

export interface UseEventStreamOptions {
  onAgentRunUpdate?: (run: AgentRunEvent) => void;
  onSystemEvent?: (event: SystemEventPayload) => void;
}

function parseJsonPayload(value: string): unknown {
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return null;
  }
}

export function useEventStream(options: UseEventStreamOptions = {}) {
  const queryClient = useQueryClient();
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY_MS);
  const [connectionState, setConnectionState] =
    useState<EventStreamConnectionState>("connecting");

  const handleAgentRunUpdate = useEffectEvent((run: AgentRunEvent) => {
    options.onAgentRunUpdate?.(run);
    void queryClient.invalidateQueries({ queryKey: getLatestAgentRunsQueryKey() });
    void queryClient.invalidateQueries({ queryKey: ["agents", "runs"] });
    void queryClient.invalidateQueries({ queryKey: ["agents", "events"] });
    void queryClient.invalidateQueries({ queryKey: ["overview", "summary"] });
    void queryClient.invalidateQueries({
      queryKey: getAgentRunDetailQueryKey(run.id),
    });
  });

  const handleSystemEvent = useEffectEvent((event: SystemEventPayload) => {
    options.onSystemEvent?.(event);
    void queryClient.invalidateQueries({ queryKey: ["agents", "events"] });
    void queryClient.invalidateQueries({ queryKey: ["incidents"] });
    void queryClient.invalidateQueries({ queryKey: ["overview", "summary"] });
    if (event.event_type === "agent_paused" || event.event_type === "agent_resumed") {
      void queryClient.invalidateQueries({ queryKey: ["agents", "pause-states"] });
    }
    if (event.agent_run_id !== null) {
      void queryClient.invalidateQueries({
        queryKey: getAgentRunDetailQueryKey(event.agent_run_id),
      });
      void queryClient.invalidateQueries({ queryKey: ["agents", "runs"] });
      void queryClient.invalidateQueries({ queryKey: getLatestAgentRunsQueryKey() });
    }
  });

  useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }

    let disposed = false;

    const clearReconnectTimer = () => {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    const closeCurrentSource = () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };

    const connect = () => {
      if (disposed || document.visibilityState === "hidden") {
        setConnectionState("closed");
        return;
      }

      clearReconnectTimer();
      closeCurrentSource();
      setConnectionState("connecting");

      const source = new EventSource(getEventStreamUrl());
      eventSourceRef.current = source;

      source.onopen = () => {
        reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS;
        setConnectionState("open");
      };

      source.onerror = () => {
        closeCurrentSource();
        if (disposed) {
          return;
        }
        setConnectionState("error");
        if (document.visibilityState === "hidden") {
          return;
        }

        const delayMs = reconnectDelayRef.current;
        reconnectDelayRef.current = Math.min(delayMs * 2, MAX_RECONNECT_DELAY_MS);
        reconnectTimerRef.current = window.setTimeout(() => {
          reconnectTimerRef.current = null;
          connect();
        }, delayMs);
      };

      const onAgentMessage = (message: MessageEvent<string>) => {
        const payload = parseJsonPayload(message.data);
        if (isAgentRunEvent(payload)) {
          handleAgentRunUpdate(payload);
        }
      };

      const onSystemMessage = (message: MessageEvent<string>) => {
        const payload = parseJsonPayload(message.data);
        if (isSystemEventPayload(payload)) {
          handleSystemEvent(payload);
        }
      };

      source.addEventListener("agent.run_started", onAgentMessage as EventListener);
      source.addEventListener("agent.run_completed", onAgentMessage as EventListener);
      source.addEventListener("agent.run_failed", onAgentMessage as EventListener);
      source.addEventListener("agent.run_skipped", onAgentMessage as EventListener);
      source.addEventListener("agent.run_skipped_paused", onAgentMessage as EventListener);
      source.addEventListener("agent.paused", onSystemMessage as EventListener);
      source.addEventListener("agent.resumed", onSystemMessage as EventListener);
      source.addEventListener("system.event", onSystemMessage as EventListener);
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        clearReconnectTimer();
        closeCurrentSource();
        setConnectionState("closed");
        return;
      }

      void queryClient.invalidateQueries({ queryKey: ["agents", "pause-states"] });
      void queryClient.invalidateQueries({ queryKey: getLatestAgentRunsQueryKey() });
      void queryClient.invalidateQueries({ queryKey: ["overview", "summary"] });
      reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS;
      connect();
    };

    connect();
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      disposed = true;
      clearReconnectTimer();
      closeCurrentSource();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [queryClient]);

  return { connectionState };
}

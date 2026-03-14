"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchIncidents, getIncidentsQueryKey, type Incident } from "@/api/incidents";
import { useEventStream } from "@/hooks/useEventStream";

export default function IncidentsClient() {
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [agentFilter, setAgentFilter] = useState<string>("");
  const [severityFilter, setSeverityFilter] = useState<string>("");
  const [classificationFilter, setClassificationFilter] = useState<string>("");
  const [eventTypeFilter, setEventTypeFilter] = useState<string>("");

  useEventStream({});

  const incidentsQuery = useQuery({
    queryKey: getIncidentsQueryKey({
      agent_name: agentFilter || undefined,
      severity: severityFilter || undefined,
      classification: classificationFilter || undefined,
      event_type: eventTypeFilter || undefined,
      limit: 50,
    }),
    queryFn: () =>
      fetchIncidents({
        agent_name: agentFilter || undefined,
        severity: severityFilter || undefined,
        classification: classificationFilter || undefined,
        event_type: eventTypeFilter || undefined,
        limit: 50,
      }),
    refetchInterval: 30_000,
  });

  const incidents = incidentsQuery.data ?? [];
  const criticalCount = incidents.filter((i) => i.severity === "critical").length;
  const errorCount = incidents.filter((i) => i.severity === "error").length;
  const warningCount = incidents.filter((i) => i.severity === "warning").length;

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <div className="mx-auto max-w-7xl">
        <h1 className="text-3xl font-bold text-slate-900">Incidents</h1>
        <p className="mt-2 text-slate-600">
          Review historical operational events and failure context
        </p>

        {/* Severity Summary Strip */}
        <div className="mt-6 grid grid-cols-3 gap-4">
          <div className="rounded-lg border border-red-200 bg-red-50 p-4">
            <div className="text-sm font-medium text-red-900">Critical</div>
            <div className="mt-1 text-2xl font-bold text-red-900">{criticalCount}</div>
          </div>
          <div className="rounded-lg border border-orange-200 bg-orange-50 p-4">
            <div className="text-sm font-medium text-orange-900">Error</div>
            <div className="mt-1 text-2xl font-bold text-orange-900">{errorCount}</div>
          </div>
          <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4">
            <div className="text-sm font-medium text-yellow-900">Warning</div>
            <div className="mt-1 text-2xl font-bold text-yellow-900">{warningCount}</div>
          </div>
        </div>

        {/* Filters */}
        <div className="mt-6 flex flex-wrap gap-4">
          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">All Agents</option>
            <option value="firehose">Firehose</option>
            <option value="backfill">Backfill</option>
            <option value="bouncer">Bouncer</option>
            <option value="analyst">Analyst</option>
          </select>
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">All Severities</option>
            <option value="critical">Critical</option>
            <option value="error">Error</option>
            <option value="warning">Warning</option>
          </select>
          <select
            value={classificationFilter}
            onChange={(e) => setClassificationFilter(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">All Classifications</option>
            <option value="retryable">Retryable</option>
            <option value="blocking">Blocking</option>
            <option value="rate_limited">Rate Limited</option>
          </select>
          <select
            value={eventTypeFilter}
            onChange={(e) => setEventTypeFilter(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">All Event Types</option>
            <option value="rate_limit_hit">Rate Limit Hit</option>
            <option value="repository_analysis_failed">Analysis Failed</option>
            <option value="repository_triage_failed">Triage Failed</option>
            <option value="repository_discovery_failed">Discovery Failed</option>
            <option value="agent_paused">Agent Paused</option>
          </select>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-6">
          {/* Incident List */}
          <div className="rounded-lg border border-slate-200 bg-white">
            <div className="border-b border-slate-200 p-4">
              <h2 className="font-semibold text-slate-900">Recent Incidents</h2>
            </div>
            <div className="max-h-[600px] overflow-y-auto">
              {incidentsQuery.isLoading ? (
                <div className="p-4 text-center text-slate-500">Loading...</div>
              ) : incidentsQuery.isError ? (
                <div className="p-4 text-center text-red-600">
                  Failed to load incidents
                </div>
              ) : incidents.length === 0 ? (
                <div className="p-4 text-center text-slate-500">No incidents found</div>
              ) : (
                <div className="divide-y divide-slate-200">
                  {incidents.map((incident) => (
                    <button
                      key={incident.id}
                      onClick={() => setSelectedIncident(incident)}
                      className={`w-full p-4 text-left transition hover:bg-slate-50 ${
                        selectedIncident?.id === incident.id ? "bg-slate-100" : ""
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span
                              className={`inline-block h-2 w-2 rounded-full ${
                                incident.severity === "critical"
                                  ? "bg-red-500"
                                  : incident.severity === "error"
                                    ? "bg-orange-500"
                                    : "bg-yellow-500"
                              }`}
                            />
                            <span className="font-medium text-slate-900">
                              {incident.agent_name}
                            </span>
                            <span className="text-xs text-slate-500">
                              {new Date(incident.created_at).toLocaleString()}
                            </span>
                          </div>
                          <p className="mt-1 text-sm text-slate-600">{incident.message}</p>
                          {incident.is_paused && (
                            <span className="mt-2 inline-block rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
                              PAUSED
                            </span>
                          )}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Detail Panel */}
          <div className="rounded-lg border border-slate-200 bg-white">
            <div className="border-b border-slate-200 p-4">
              <h2 className="font-semibold text-slate-900">Incident Details</h2>
            </div>
            <div className="max-h-[600px] overflow-y-auto p-4">
              {selectedIncident ? (
                <div className="space-y-4">
                  <div>
                    <h3 className="text-sm font-medium text-slate-700">Event Type</h3>
                    <p className="mt-1 text-sm text-slate-900">
                      {selectedIncident.event_type}
                    </p>
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-slate-700">Message</h3>
                    <p className="mt-1 text-sm text-slate-900">{selectedIncident.message}</p>
                  </div>
                  {selectedIncident.failure_classification && (
                    <div>
                      <h3 className="text-sm font-medium text-slate-700">Classification</h3>
                      <p className="mt-1 text-sm text-slate-900">
                        {selectedIncident.failure_classification}
                      </p>
                    </div>
                  )}
                  {selectedIncident.agent_run_id && (
                    <div>
                      <h3 className="text-sm font-medium text-slate-700">Run Details</h3>
                      <div className="mt-1 space-y-1 text-sm text-slate-900">
                        <p>Run ID: {selectedIncident.agent_run_id}</p>
                        {selectedIncident.run_status && (
                          <p>Status: {selectedIncident.run_status}</p>
                        )}
                        {selectedIncident.run_duration_seconds !== null && (
                          <p>Duration: {selectedIncident.run_duration_seconds.toFixed(2)}s</p>
                        )}
                        {selectedIncident.run_error_summary && (
                          <p>Error: {selectedIncident.run_error_summary}</p>
                        )}
                        {selectedIncident.run_error_context && (
                          <div className="text-xs text-slate-600">
                            <p className="font-medium">Context:</p>
                            <pre className="mt-1 whitespace-pre-wrap break-words">
                              {(() => {
                                try {
                                  return JSON.stringify(JSON.parse(selectedIncident.run_error_context), null, 2);
                                } catch {
                                  return selectedIncident.run_error_context;
                                }
                              })()}
                            </pre>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  {selectedIncident.repository_full_name && (
                    <div>
                      <h3 className="text-sm font-medium text-slate-700">Repository</h3>
                      <p className="mt-1 text-sm text-slate-900">
                        {selectedIncident.repository_full_name}
                      </p>
                    </div>
                  )}
                  {selectedIncident.is_paused && (
                    <div>
                      <h3 className="text-sm font-medium text-slate-700">Pause Status</h3>
                      <p className="mt-1 text-sm text-slate-900">
                        {selectedIncident.pause_reason}
                      </p>
                      <p className="mt-1 text-sm text-slate-600">
                        Resume: {selectedIncident.resume_condition}
                      </p>
                    </div>
                  )}
                  {selectedIncident.checkpoint_context && (
                    <div>
                      <h3 className="text-sm font-medium text-slate-700">
                        Checkpoint Context
                      </h3>
                      <div className="mt-1 space-y-1 text-sm text-slate-900">
                        {selectedIncident.checkpoint_context.mode && (
                          <p>Mode: {selectedIncident.checkpoint_context.mode}</p>
                        )}
                        {selectedIncident.checkpoint_context.page !== null && (
                          <p>Page: {selectedIncident.checkpoint_context.page}</p>
                        )}
                        {selectedIncident.checkpoint_context.anchor_date && (
                          <p>Anchor: {selectedIncident.checkpoint_context.anchor_date}</p>
                        )}
                        {selectedIncident.checkpoint_context.window_start && (
                          <p>Window Start: {selectedIncident.checkpoint_context.window_start}</p>
                        )}
                        {selectedIncident.checkpoint_context.window_end && (
                          <p>Window End: {selectedIncident.checkpoint_context.window_end}</p>
                        )}
                        {selectedIncident.checkpoint_context.resume_required !== null && (
                          <p>Resume Required: {selectedIncident.checkpoint_context.resume_required ? "Yes" : "No"}</p>
                        )}
                      </div>
                    </div>
                  )}
                  {selectedIncident.routing_context && (
                    <div>
                      <h3 className="text-sm font-medium text-slate-700">Routing Context</h3>
                      <div className="mt-1 space-y-1 text-sm text-slate-900">
                        {selectedIncident.routing_context.session_id && (
                          <p>Session: {selectedIncident.routing_context.session_id}</p>
                        )}
                        {selectedIncident.routing_context.route_key && (
                          <p>Route: {selectedIncident.routing_context.route_key}</p>
                        )}
                        {selectedIncident.routing_context.agent_key && (
                          <p>Agent: {selectedIncident.routing_context.agent_key}</p>
                        )}
                      </div>
                    </div>
                  )}
                  {selectedIncident.next_action && (
                    <div className="rounded-lg bg-blue-50 p-3">
                      <h3 className="text-sm font-medium text-blue-900">Next Action</h3>
                      <p className="mt-1 text-sm text-blue-800">
                        {selectedIncident.next_action}
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-center text-slate-500">
                  Select an incident to view details
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

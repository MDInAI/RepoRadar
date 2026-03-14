"use client";

import {
  type SortingState,
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useState } from "react";

import {
  AGENT_DISPLAY_ORDER,
  type AgentName,
  type AgentRunEvent,
  type AgentRunStatus,
} from "@/api/agents";

import {
  formatAgentName,
  formatAgentRunStatus,
  formatItemsCount,
  formatRunDuration,
  formatTimestampLabel,
  getRunStatusBadgeClassName,
} from "./agentPresentation";

const columnHelper = createColumnHelper<AgentRunEvent>();

const columns = [
  columnHelper.accessor("agent_name", {
    header: "Agent",
    cell: (info) => (
      <span className="font-semibold text-slate-950">{formatAgentName(info.getValue())}</span>
    ),
  }),
  columnHelper.accessor("status", {
    header: "Status",
    cell: (info) => (
      <span
        className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${getRunStatusBadgeClassName(
          info.getValue(),
        )}`}
      >
        {formatAgentRunStatus(info.getValue())}
      </span>
    ),
  }),
  columnHelper.accessor("started_at", {
    header: "Started",
    cell: (info) => <span className="text-sm text-slate-700">{formatTimestampLabel(info.getValue())}</span>,
  }),
  columnHelper.display({
    id: "duration",
    header: "Duration",
    cell: (info) => (
      <span className="text-sm text-slate-700">
        {formatRunDuration(info.row.original.duration_seconds)}
      </span>
    ),
  }),
  columnHelper.display({
    id: "items",
    header: "Items",
    cell: (info) => {
      const run = info.row.original;
      return (
        <span className="text-sm text-slate-700">
          {formatItemsCount(run.items_processed)} / {formatItemsCount(run.items_succeeded)} /{" "}
          {formatItemsCount(run.items_failed)}
        </span>
      );
    },
  }),
  columnHelper.accessor("error_summary", {
    header: "Error Summary",
    cell: (info) => (
      <span className="line-clamp-2 text-sm text-slate-600">
        {info.getValue() ?? "No error summary"}
      </span>
    ),
  }),
];

export function AgentRunHistoryTable({
  agentFilter,
  canLoadMore,
  isLoading,
  isLoadingMore,
  onAgentFilterChange,
  onLoadMore,
  onStatusFilterChange,
  runs,
  statusFilter,
}: {
  agentFilter: AgentName | null;
  canLoadMore: boolean;
  isLoading: boolean;
  isLoadingMore: boolean;
  onAgentFilterChange: (value: AgentName | null) => void;
  onLoadMore: () => void;
  onStatusFilterChange: (value: AgentRunStatus | null) => void;
  runs: AgentRunEvent[];
  statusFilter: AgentRunStatus | null;
}) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "started_at", desc: true }]);

  // TanStack Table remains the supported integration point for the dense run-history grid.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: runs,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <section className="rounded-[2rem] border border-black/10 bg-white/90 p-5 shadow-[0_24px_70px_-40px_rgba(15,23,42,0.55)]">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-orange-700">
            Run History
          </p>
          <p className="mt-2 text-sm text-slate-600">
            Recent agent executions with status, duration, item counts, and failure summaries.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm text-slate-600">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
              Agent
            </span>
            <select
              aria-label="Filter run history by agent"
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
              value={agentFilter ?? ""}
              onChange={(event) =>
                onAgentFilterChange(
                  event.target.value ? (event.target.value as AgentName) : null,
                )
              }
            >
              <option value="">All agents</option>
              {AGENT_DISPLAY_ORDER.map((agentName) => (
                <option key={agentName} value={agentName}>
                  {formatAgentName(agentName)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm text-slate-600">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
              Status
            </span>
            <select
              aria-label="Filter run history by status"
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
              value={statusFilter ?? ""}
              onChange={(event) =>
                onStatusFilterChange(
                  event.target.value ? (event.target.value as AgentRunStatus) : null,
                )
              }
            >
              <option value="">All statuses</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="skipped">Skipped</option>
              <option value="skipped_paused">Skipped (Paused)</option>
            </select>
          </label>
        </div>
      </div>

      <div className="mt-5 overflow-hidden rounded-[1.6rem] border border-slate-200">
        <table className="min-w-full border-separate border-spacing-0">
          <thead className="bg-slate-950 text-left text-xs uppercase tracking-[0.22em] text-slate-300">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th key={header.id} className="px-4 py-4 font-semibold first:pl-5 last:pr-5">
                    {header.isPlaceholder ? null : (
                      <button
                        className="inline-flex items-center gap-2"
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                      </button>
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td className="px-5 py-6 text-sm text-slate-600" colSpan={columns.length}>
                  Loading recent agent runs.
                </td>
              </tr>
            ) : null}

            {!isLoading && table.getRowModel().rows.length === 0 ? (
              <tr>
                <td className="px-5 py-6 text-sm text-slate-600" colSpan={columns.length}>
                  No runs match the current filters.
                </td>
              </tr>
            ) : null}

            {!isLoading
              ? table.getRowModel().rows.map((row, index) => (
                  <tr
                    key={row.id}
                    className={index % 2 === 0 ? "bg-white" : "bg-slate-50/70"}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-4 py-4 align-top first:pl-5 last:pr-5">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))
              : null}
          </tbody>
        </table>
      </div>

      <div className="mt-5 flex flex-col gap-3 border-t border-slate-200 pt-5 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-slate-600">
          Showing {runs.length} run{runs.length === 1 ? "" : "s"} from the latest query window.
        </p>
        {canLoadMore ? (
          <button
            className="rounded-full border border-slate-950 bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isLoadingMore}
            type="button"
            onClick={onLoadMore}
          >
            {isLoadingMore ? "Loading more" : "Load 50 more"}
          </button>
        ) : null}
      </div>
    </section>
  );
}

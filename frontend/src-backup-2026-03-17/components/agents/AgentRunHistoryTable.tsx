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
} from "./agentPresentation";

const columnHelper = createColumnHelper<AgentRunEvent>();

const columns = [
  columnHelper.accessor("agent_name", {
    header: "Agent",
    cell: (info) => (
      <span style={{ fontWeight: 500, color: 'var(--text-0)', whiteSpace: 'nowrap' }}>{formatAgentName(info.getValue())}</span>
    ),
  }),
  columnHelper.accessor("status", {
    header: "Status",
    cell: (info) => (
      <span className="run-status-badge" data-status={info.getValue()}>
        {formatAgentRunStatus(info.getValue())}
      </span>
    ),
  }),
  columnHelper.accessor("started_at", {
    header: "Started",
    cell: (info) => <span style={{ fontSize: '11px', fontFamily: 'var(--mono)', color: 'var(--text-2)', whiteSpace: 'nowrap' }}>{formatTimestampLabel(info.getValue())}</span>,
  }),
  columnHelper.display({
    id: "duration",
    header: "Duration",
    cell: (info) => (
      <span style={{ fontSize: '11px', fontFamily: 'var(--mono)', color: 'var(--text-2)', whiteSpace: 'nowrap' }}>
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
        <span style={{ fontSize: '11px', fontFamily: 'var(--mono)', color: 'var(--text-1)', whiteSpace: 'nowrap' }}>
          {formatItemsCount(run.items_processed)} / {formatItemsCount(run.items_succeeded)} / {formatItemsCount(run.items_failed)}
        </span>
      );
    },
  }),
  columnHelper.accessor("error_summary", {
    header: "Error Summary",
    cell: (info) => (
      <span style={{ fontSize: '12px', color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {info.getValue() ?? "—"}
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
    <div>
      <div className="filter-bar" style={{ marginBottom: '12px' }}>
        <select
          className="select"
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
        <select
          className="select"
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
      </div>

      <div style={{ maxHeight: '500px', overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', background: 'var(--bg-2)' }}>
        <table className="run-history-table" style={{ tableLayout: 'fixed', width: '100%', borderCollapse: 'collapse' }}>
          <colgroup>
            <col style={{ width: '120px' }} />
            <col style={{ width: '95px' }} />
            <col style={{ width: '135px' }} />
            <col style={{ width: '85px' }} />
            <col style={{ width: '130px' }} />
            <col />
          </colgroup>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th key={header.id}>
                    {header.isPlaceholder ? null : (
                      <button
                        style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0, font: 'inherit', textAlign: 'left', width: '100%' }}
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
                <td colSpan={columns.length} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-3)' }}>
                  Loading recent agent runs.
                </td>
              </tr>
            ) : null}

            {!isLoading && table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-3)' }}>
                  No runs match the current filters.
                </td>
              </tr>
            ) : null}

            {!isLoading
              ? table.getRowModel().rows.map((row) => (
                  <tr key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))
              : null}
          </tbody>
        </table>
      </div>

      <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-3)', fontFamily: 'var(--mono)' }}>
          {runs.length} run{runs.length === 1 ? "" : "s"}
        </span>
        {canLoadMore ? (
          <button
            className="btn btn-sm"
            disabled={isLoadingMore}
            type="button"
            onClick={onLoadMore}
          >
            {isLoadingMore ? "Loading..." : "Load 50 more"}
          </button>
        ) : null}
      </div>
    </div>
  );
}

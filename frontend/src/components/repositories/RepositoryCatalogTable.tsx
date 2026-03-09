import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";

import type { RepositoryCatalogItem } from "@/api/repositories";

import {
  formatAnalysisStatusLabel,
  formatCompactNumber,
  formatDiscoverySourceLabel,
  formatMonetizationLabel,
  formatRelativeDate,
  getFitBadgeClassName,
  getSourceBadgeClassName,
  getStatusBadgeClassName,
} from "./catalogPresentation";

const columnHelper = createColumnHelper<RepositoryCatalogItem>();

const columns = [
  columnHelper.accessor("full_name", {
    header: "Repository",
    cell: (info) => (
      <div className="min-w-[18rem]">
        <p className="font-semibold text-slate-950">{info.getValue()}</p>
        <p className="mt-1 line-clamp-2 text-sm text-slate-600">
          {info.row.original.repository_description ?? "No description available."}
        </p>
      </div>
    ),
  }),
  columnHelper.accessor("monetization_potential", {
    header: "Monetization Fit",
    cell: (info) => (
      <span
        className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${getFitBadgeClassName(
          info.getValue(),
        )}`}
      >
        {formatMonetizationLabel(info.getValue())}
      </span>
    ),
  }),
  columnHelper.accessor("stargazers_count", {
    header: "Stars",
    cell: (info) => <span className="font-medium text-slate-900">{formatCompactNumber(info.getValue())}</span>,
  }),
  columnHelper.accessor("forks_count", {
    header: "Forks",
    cell: (info) => <span className="font-medium text-slate-900">{formatCompactNumber(info.getValue())}</span>,
  }),
  columnHelper.accessor("discovery_source", {
    header: "Source",
    cell: (info) => (
      <span
        className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${getSourceBadgeClassName(
          info.getValue(),
        )}`}
      >
        {formatDiscoverySourceLabel(info.getValue())}
      </span>
    ),
  }),
  columnHelper.accessor("analysis_status", {
    header: "Analysis Status",
    cell: (info) => (
      <span
        className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${getStatusBadgeClassName(
          info.getValue(),
        )}`}
      >
        {formatAnalysisStatusLabel(info.getValue())}
      </span>
    ),
  }),
  columnHelper.accessor("pushed_at", {
    header: "Pushed At",
    cell: (info) => <span className="text-sm text-slate-600">{formatRelativeDate(info.getValue())}</span>,
  }),
];

export function RepositoryCatalogTable({
  items,
  onRowClick,
}: {
  items: RepositoryCatalogItem[];
  onRowClick: (repositoryId: number) => void;
}) {
  // TanStack Table's hook is the supported integration point for this client-only grid.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: items,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="overflow-hidden rounded-[2rem] border border-black/10 bg-white/90 shadow-[0_24px_70px_-40px_rgba(15,23,42,0.55)]">
      <table className="min-w-full border-separate border-spacing-0">
        <thead className="bg-slate-950 text-left text-xs uppercase tracking-[0.22em] text-slate-300">
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th key={header.id} className="px-4 py-4 font-semibold first:pl-6 last:pr-6">
                  {header.isPlaceholder
                    ? null
                    : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row, index) => (
            <tr
              key={row.id}
              className={`cursor-pointer transition hover:bg-orange-50 ${
                index % 2 === 0 ? "bg-white" : "bg-slate-50/60"
              }`}
              onClick={() => onRowClick(row.original.github_repository_id)}
            >
              {row.getVisibleCells().map((cell) => (
                <td
                  key={cell.id}
                  className="border-t border-slate-200 px-4 py-4 align-top text-sm first:pl-6 last:pr-6"
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

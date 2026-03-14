import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";

import type { RepositoryCatalogItem } from "@/api/repositories";

import {
  formatAnalysisStatusLabel,
  formatCompactNumber,
  formatDiscoverySourceLabel,
  formatMonetizationLabel,
  formatQueueStatusLabel,
  formatTriageStatusLabel,
  formatRelativeDate,
  getFitBadgeClassName,
  getQueueStatusBadgeClassName,
  getSourceBadgeClassName,
  getStatusBadgeClassName,
  getTriageStatusBadgeClassName,
} from "./catalogPresentation";

const columnHelper = createColumnHelper<RepositoryCatalogItem>();

function truncateFailureMessage(value: string | null): string {
  if (!value) {
    return "No failure message recorded.";
  }
  return value.length > 72 ? `${value.slice(0, 69)}...` : value;
}

function formatFailureCode(value: string): string {
  return value
    .split("_")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function formatFailureTimestamp(value: string | null): string {
  if (!value) {
    return "Timestamp unavailable";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown timestamp";
  }

  return `${parsed.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function getFailureContext(item: RepositoryCatalogItem) {
  return item.failure;
}

function StarIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      aria-hidden="true"
      className="h-5 w-5"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={1.8}
      viewBox="0 0 24 24"
    >
      <path
        d="M12 3.75l2.55 5.17 5.7.83-4.13 4.03.98 5.67L12 16.77 6.9 19.45l.98-5.67-4.13-4.03 5.7-.83L12 3.75z"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const columns = [
  columnHelper.display({
    id: "select",
    header: ({ table }) => {
      const meta = table.options.meta as { selectedIds?: Set<number>; onToggleSelection?: (id: number) => void } | undefined;
      if (!meta?.selectedIds || !meta?.onToggleSelection) return null;
      return (
        <input
          type="checkbox"
          checked={table.getRowModel().rows.every((row) => meta.selectedIds?.has(row.original.github_repository_id))}
          onChange={(e) => {
            table.getRowModel().rows.forEach((row) => {
              const id = row.original.github_repository_id;
              const isSelected = meta.selectedIds?.has(id);
              if (e.target.checked && !isSelected) {
                meta.onToggleSelection?.(id);
              } else if (!e.target.checked && isSelected) {
                meta.onToggleSelection?.(id);
              }
            });
          }}
        />
      );
    },
    cell: (info) => {
      const meta = info.table.options.meta as { selectedIds?: Set<number>; onToggleSelection?: (id: number) => void } | undefined;
      if (!meta?.selectedIds || !meta?.onToggleSelection) return null;
      const id = info.row.original.github_repository_id;
      return (
        <input
          type="checkbox"
          checked={meta.selectedIds.has(id)}
          onChange={() => meta.onToggleSelection?.(id)}
          onClick={(e) => e.stopPropagation()}
        />
      );
    },
  }),
  columnHelper.display({
    id: "starred",
    header: "Starred",
    cell: (info) => {
      const item = info.row.original;
      const meta = info.table.options.meta as
        | {
            toggleStar?: (repositoryId: number, starred: boolean) => void;
            togglingRepositoryId?: number | null;
          }
        | undefined;
      const toggleStar = meta?.toggleStar;
      const isToggling = meta?.togglingRepositoryId === item.github_repository_id;

      return (
        <button
          aria-label={item.is_starred ? "Unstar repository" : "Star repository"}
          aria-pressed={item.is_starred}
          className={`inline-flex h-10 w-10 items-center justify-center rounded-full border transition ${
            item.is_starred
              ? "border-amber-300 bg-amber-50 text-amber-600 hover:bg-amber-100"
              : "border-slate-200 bg-white text-slate-400 hover:border-amber-300 hover:text-amber-500"
          }`}
          disabled={isToggling || !toggleStar}
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            toggleStar?.(item.github_repository_id, !item.is_starred);
          }}
        >
          <StarIcon filled={item.is_starred} />
        </button>
      );
    },
  }),
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
  columnHelper.display({
    id: "intake_status",
    header: "Intake Status",
    cell: (info) => (
      <span
        className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${getQueueStatusBadgeClassName(
          info.row.original.intake_status,
        )}`}
      >
        {formatQueueStatusLabel(info.row.original.intake_status)}
      </span>
    ),
  }),
  columnHelper.accessor("triage_status", {
    header: "Triage Status",
    cell: (info) => (
      <span
        className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${getTriageStatusBadgeClassName(
          info.getValue(),
        )}`}
      >
        {formatTriageStatusLabel(info.getValue())}
      </span>
    ),
  }),
  columnHelper.accessor("analysis_status", {
    header: "Analysis Status",
    cell: (info) => {
      const failure = info.row.original.failure;
      const tooltipMessage =
        failure?.stage === "analysis" && failure.error_code
          ? `${failure.error_code}: ${truncateFailureMessage(failure.error_message)}`
          : null;

      return (
        <div className="flex min-w-[11rem] flex-col gap-2">
          <span
            className={`inline-flex w-fit rounded-full border px-2.5 py-1 text-xs font-semibold ${getStatusBadgeClassName(
              info.getValue(),
            )}`}
          >
            {formatAnalysisStatusLabel(info.getValue())}
          </span>
          {failure?.stage === "analysis" && failure.error_code ? (
            <span
              className="inline-flex w-fit rounded-full border border-rose-300 bg-rose-100 px-2.5 py-1 text-xs font-semibold text-rose-900"
              title={tooltipMessage ?? undefined}
            >
              Failure: {formatFailureCode(failure.error_code)}
            </span>
          ) : null}
        </div>
      );
    },
  }),
  columnHelper.display({
    id: "processing_window",
    header: "Processing Window",
    cell: (info) => (
      <div className="min-w-[12rem] space-y-1 text-sm text-slate-600">
        <p>Queued {formatRelativeDate(info.row.original.queue_created_at)}</p>
        <p>Started {formatRelativeDate(info.row.original.processing_started_at)}</p>
        <p>Completed {formatRelativeDate(info.row.original.processing_completed_at)}</p>
      </div>
    ),
  }),
  columnHelper.display({
    id: "failure_details",
    header: "Failure Details",
    cell: (info) => {
      const failure = getFailureContext(info.row.original);

      if (!failure) {
        return <span className="text-sm text-slate-400">No failures</span>;
      }

      return (
        <div className="flex min-w-[18rem] flex-col gap-1.5">
          <span className="inline-flex w-fit rounded-full border border-rose-300 bg-rose-100 px-2.5 py-1 text-xs font-semibold text-rose-900">
            {failure.stage === "analysis" ? "Analysis Failure" : "Intake Failure"}
          </span>
          <p className="text-sm font-semibold text-slate-900">
            {formatFailureCode(failure.error_code ?? `${failure.stage}_failed`)}
          </p>
          <p
            className="line-clamp-2 text-sm text-slate-600"
            title={failure.error_message ?? undefined}
          >
            {failure.error_message ?? "No failure message recorded."}
          </p>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
            Failed At {formatFailureTimestamp(failure.failed_at)}
          </p>
        </div>
      );
    },
  }),
  columnHelper.accessor("user_tags", {
    header: "User Tags",
    cell: (info) => {
      const tags = info.getValue();
      if (tags.length === 0) {
        return <span className="text-sm text-slate-400">No tags</span>;
      }

      return (
        <div className="flex max-w-[14rem] flex-wrap gap-2">
          {tags.map((tag) => (
            <span
              key={tag}
              className="rounded-full border border-orange-200 bg-orange-50 px-2.5 py-1 text-xs font-semibold text-orange-900"
            >
              {tag}
            </span>
          ))}
        </div>
      );
    },
  }),
  columnHelper.accessor("pushed_at", {
    header: "Pushed At",
    cell: (info) => <span className="text-sm text-slate-600">{formatRelativeDate(info.getValue())}</span>,
  }),
];

export function RepositoryCatalogTable({
  items,
  selectedIds,
  onToggleSelection,
  onToggleStar,
  togglingRepositoryId,
  onRowClick,
}: {
  items: RepositoryCatalogItem[];
  selectedIds?: Set<number>;
  onToggleSelection?: (repositoryId: number) => void;
  onToggleStar: (repositoryId: number, starred: boolean) => void;
  togglingRepositoryId: number | null;
  onRowClick: (repositoryId: number) => void;
}) {
  // TanStack Table's hook is the supported integration point for this client-only grid.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: items,
    columns,
    getCoreRowModel: getCoreRowModel(),
    meta: {
      selectedIds,
      onToggleSelection,
      toggleStar: onToggleStar,
      togglingRepositoryId,
    },
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

import type {
  RepositoryAnalysisStatus,
  RepositoryCatalogFilterChip,
  RepositoryCatalogSortBy,
  RepositoryCatalogSortOrder,
  RepositoryDiscoverySource,
  RepositoryMonetizationPotential,
  RepositoryTriageStatus,
} from "@/api/repositories";

const SOURCE_OPTIONS: Array<{
  label: string;
  value: RepositoryDiscoverySource | "";
}> = [
  { label: "All Sources", value: "" },
  { label: "Firehose", value: "firehose" },
  { label: "Backfill", value: "backfill" },
];

const TRIAGE_OPTIONS: Array<{
  label: string;
  value: RepositoryTriageStatus | "";
}> = [
  { label: "All Triage", value: "" },
  { label: "Accepted", value: "accepted" },
  { label: "Rejected", value: "rejected" },
  { label: "Pending", value: "pending" },
];

const ANALYSIS_OPTIONS: Array<{
  label: string;
  value: RepositoryAnalysisStatus | "";
}> = [
  { label: "All Analysis", value: "" },
  { label: "Completed", value: "completed" },
  { label: "In Progress", value: "in_progress" },
  { label: "Pending", value: "pending" },
  { label: "Failed", value: "failed" },
];

const MONETIZATION_OPTIONS: Array<{
  label: string;
  value: RepositoryMonetizationPotential | "";
}> = [
  { label: "All Fit Scores", value: "" },
  { label: "High", value: "high" },
  { label: "Medium", value: "medium" },
  { label: "Low", value: "low" },
];

const SORT_OPTIONS: Array<{
  label: string;
  value: RepositoryCatalogSortBy;
}> = [
  { label: "Stars", value: "stars" },
  { label: "Forks", value: "forks" },
  { label: "Pushed At", value: "pushed_at" },
  { label: "Ingested", value: "ingested_at" },
];

function ToolbarSelect({
  ariaLabel,
  value,
  options,
  onChange,
}: {
  ariaLabel: string;
  value: string;
  options: Array<{ label: string; value: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex min-w-0 flex-1 flex-col gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
      <span>{ariaLabel}</span>
      <select
        aria-label={ariaLabel}
        className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium normal-case tracking-normal text-slate-900 shadow-sm outline-none transition focus:border-orange-400"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option.label} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function CatalogFilterBar({
  searchValue,
  source,
  triageStatus,
  analysisStatus,
  monetization,
  minStars,
  maxStars,
  sort,
  order,
  visibleCount,
  totalCount,
  chips,
  isRefreshing,
  validationMessage,
  onSearchChange,
  onSourceChange,
  onTriageStatusChange,
  onAnalysisStatusChange,
  onMonetizationChange,
  onMinStarsChange,
  onMaxStarsChange,
  onSortChange,
  onOrderChange,
  onRemoveChip,
  onClearAll,
}: {
  searchValue: string;
  source: RepositoryDiscoverySource | null;
  triageStatus: RepositoryTriageStatus | null;
  analysisStatus: RepositoryAnalysisStatus | null;
  monetization: RepositoryMonetizationPotential | null;
  minStars: number | null;
  maxStars: number | null;
  sort: RepositoryCatalogSortBy;
  order: RepositoryCatalogSortOrder;
  visibleCount: number;
  totalCount: number;
  chips: RepositoryCatalogFilterChip[];
  isRefreshing: boolean;
  validationMessage: string | null;
  onSearchChange: (value: string) => void;
  onSourceChange: (value: RepositoryDiscoverySource | null) => void;
  onTriageStatusChange: (value: RepositoryTriageStatus | null) => void;
  onAnalysisStatusChange: (value: RepositoryAnalysisStatus | null) => void;
  onMonetizationChange: (value: RepositoryMonetizationPotential | null) => void;
  onMinStarsChange: (value: number | null) => void;
  onMaxStarsChange: (value: number | null) => void;
  onSortChange: (value: RepositoryCatalogSortBy) => void;
  onOrderChange: (value: RepositoryCatalogSortOrder) => void;
  onRemoveChip: (key: RepositoryCatalogFilterChip["key"]) => void;
  onClearAll: () => void;
}) {
  return (
    <section className="rounded-[2rem] border border-black/10 bg-white/85 p-5 shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)] backdrop-blur">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end">
        <label className="flex min-w-0 flex-[1.5] flex-col gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
          <span>Search</span>
          <input
            aria-label="Search repositories"
            className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium normal-case tracking-normal text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-orange-400"
            placeholder="Search name or description"
            type="search"
            value={searchValue}
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </label>

        <ToolbarSelect
          ariaLabel="Discovery source"
          value={source ?? ""}
          options={SOURCE_OPTIONS}
          onChange={(value) => onSourceChange((value || null) as RepositoryDiscoverySource | null)}
        />
        <ToolbarSelect
          ariaLabel="Monetization fit"
          value={monetization ?? ""}
          options={MONETIZATION_OPTIONS}
          onChange={(value) =>
            onMonetizationChange((value || null) as RepositoryMonetizationPotential | null)
          }
        />
        <ToolbarSelect
          ariaLabel="Sort by"
          value={sort}
          options={SORT_OPTIONS}
          onChange={(value) => onSortChange(value as RepositoryCatalogSortBy)}
        />

        <button
          aria-label="Toggle sort order"
          className="inline-flex h-[3.15rem] min-w-[9rem] items-center justify-center rounded-2xl border border-slate-200 bg-slate-950 px-4 text-sm font-semibold text-white transition hover:bg-slate-800"
          type="button"
          onClick={() => onOrderChange(order === "desc" ? "asc" : "desc")}
        >
          {order === "desc" ? "Descending" : "Ascending"}
        </button>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <ToolbarSelect
          ariaLabel="Triage status"
          value={triageStatus ?? ""}
          options={TRIAGE_OPTIONS}
          onChange={(value) => onTriageStatusChange((value || null) as RepositoryTriageStatus | null)}
        />
        <ToolbarSelect
          ariaLabel="Analysis status"
          value={analysisStatus ?? ""}
          options={ANALYSIS_OPTIONS}
          onChange={(value) =>
            onAnalysisStatusChange((value || null) as RepositoryAnalysisStatus | null)
          }
        />
        <label className="flex min-w-0 flex-col gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
          <span>Minimum stars</span>
          <input
            aria-label="Minimum stars"
            className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium normal-case tracking-normal text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-orange-400"
            min={0}
            placeholder="No threshold"
            type="number"
            value={minStars ?? ""}
            onChange={(event) => {
              const nextValue = event.target.value;
              onMinStarsChange(nextValue === "" ? null : Number.parseInt(nextValue, 10));
            }}
          />
        </label>
        <label className="flex min-w-0 flex-col gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
          <span>Maximum stars</span>
          <input
            aria-label="Maximum stars"
            className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium normal-case tracking-normal text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-orange-400"
            min={0}
            placeholder="No ceiling"
            type="number"
            value={maxStars ?? ""}
            onChange={(event) => {
              const nextValue = event.target.value;
              onMaxStarsChange(nextValue === "" ? null : Number.parseInt(nextValue, 10));
            }}
          />
        </label>
      </div>

      {validationMessage ? (
        <p
          aria-live="polite"
          className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-950"
        >
          {validationMessage}
        </p>
      ) : null}

      <div className="mt-5 flex flex-col gap-3 border-t border-slate-200/80 pt-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {chips.length === 0 ? (
            <span className="rounded-full border border-dashed border-slate-300 px-3 py-1 text-xs font-medium text-slate-500">
              No active filters
            </span>
          ) : (
            chips.map((chip) => (
              <button
                key={chip.label}
                aria-label={`Remove ${chip.label} filter`}
                className="inline-flex items-center gap-2 rounded-full border border-orange-200 bg-orange-50 px-3 py-1.5 text-xs font-semibold text-orange-900 transition hover:border-orange-300 hover:bg-orange-100"
                type="button"
                onClick={() => onRemoveChip(chip.key)}
              >
                <span>{chip.label}</span>
                <span aria-hidden="true">x</span>
              </button>
            ))
          )}
          {chips.length > 1 ? (
            <button
              className="inline-flex items-center rounded-full border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-slate-400 hover:bg-slate-100"
              type="button"
              onClick={onClearAll}
            >
              Clear all
            </button>
          ) : null}
        </div>

        <div className="flex items-center gap-3 text-sm text-slate-600">
          <span className="font-semibold text-slate-900">
            Showing {visibleCount} of {totalCount} repos
          </span>
          {isRefreshing ? (
            <span className="rounded-full bg-slate-950 px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-white">
              Refreshing
            </span>
          ) : null}
        </div>
      </div>
    </section>
  );
}

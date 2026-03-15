import type {
  RepositoryAnalysisStatus,
  RepositoryCatalogFilterChip,
  RepositoryCatalogSortBy,
  RepositoryCatalogSortOrder,
  RepositoryCategory,
  RepositoryDiscoverySource,
  RepositoryMonetizationPotential,
  RepositoryQueueStatus,
  RepositoryTriageStatus,
} from "@/api/repositories";

const SOURCE_OPTIONS: Array<{ label: string; value: RepositoryDiscoverySource | "" }> = [
  { label: "All sources", value: "" },
  { label: "Firehose", value: "firehose" },
  { label: "Backfill", value: "backfill" },
];

const CATEGORY_OPTIONS: Array<{ label: string; value: RepositoryCategory | "" }> = [
  { label: "All categories", value: "" },
  { label: "Workflow", value: "workflow" },
  { label: "Analytics", value: "analytics" },
  { label: "DevOps", value: "devops" },
  { label: "Infrastructure", value: "infrastructure" },
  { label: "DevTools", value: "devtools" },
  { label: "CRM", value: "crm" },
  { label: "Communication", value: "communication" },
  { label: "Support", value: "support" },
  { label: "Observability", value: "observability" },
  { label: "Low-Code", value: "low_code" },
  { label: "Security", value: "security" },
  { label: "AI / ML", value: "ai_ml" },
  { label: "Data", value: "data" },
  { label: "Productivity", value: "productivity" },
];

const TRIAGE_OPTIONS: Array<{ label: string; value: RepositoryTriageStatus | "" }> = [
  { label: "All triage", value: "" },
  { label: "Accepted", value: "accepted" },
  { label: "Rejected", value: "rejected" },
  { label: "Pending", value: "pending" },
];

const QUEUE_OPTIONS: Array<{ label: string; value: RepositoryQueueStatus | "" }> = [
  { label: "All queue", value: "" },
  { label: "Pending", value: "pending" },
  { label: "In progress", value: "in_progress" },
  { label: "Completed", value: "completed" },
  { label: "Failed", value: "failed" },
];

const ANALYSIS_OPTIONS: Array<{ label: string; value: RepositoryAnalysisStatus | "" }> = [
  { label: "All analysis", value: "" },
  { label: "Completed", value: "completed" },
  { label: "In progress", value: "in_progress" },
  { label: "Pending", value: "pending" },
  { label: "Failed", value: "failed" },
];

const MONETIZATION_OPTIONS: Array<{
  label: string;
  value: RepositoryMonetizationPotential | "";
}> = [
  { label: "All fit scores", value: "" },
  { label: "High", value: "high" },
  { label: "Medium", value: "medium" },
  { label: "Low", value: "low" },
];

const SORT_OPTIONS: Array<{ label: string; value: RepositoryCatalogSortBy }> = [
  { label: "Stars", value: "stars" },
  { label: "Forks", value: "forks" },
  { label: "Pushed At", value: "pushed_at" },
  { label: "Ingested", value: "ingested_at" },
];

function FilterSelect({
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
    <label className="repo-filter-control">
      <span className="repo-filter-label">{ariaLabel}</span>
      <select aria-label={ariaLabel} className="select" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.label} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function FilterInput({
  ariaLabel,
  value,
  placeholder,
  onChange,
}: {
  ariaLabel: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="repo-filter-control">
      <span className="repo-filter-label">{ariaLabel}</span>
      <input
        aria-label={ariaLabel}
        className="input"
        placeholder={placeholder}
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

export function CatalogFilterBar({
  searchValue,
  source,
  category,
  agentTag,
  userTag,
  queueStatus,
  triageStatus,
  analysisStatus,
  hasFailures,
  monetization,
  minStars,
  maxStars,
  starredOnly,
  sort,
  order,
  visibleCount,
  totalCount,
  chips,
  isRefreshing,
  validationMessage,
  onSearchChange,
  onSourceChange,
  onCategoryChange,
  onAgentTagChange,
  onUserTagChange,
  onQueueStatusChange,
  onTriageStatusChange,
  onAnalysisStatusChange,
  onHasFailuresChange,
  onMonetizationChange,
  onMinStarsChange,
  onMaxStarsChange,
  onStarredOnlyChange,
  onSortChange,
  onOrderChange,
  onRemoveChip,
  onClearAll,
}: {
  searchValue: string;
  source: RepositoryDiscoverySource | null;
  category: RepositoryCategory | null;
  agentTag: string | null;
  userTag: string | null;
  queueStatus: RepositoryQueueStatus | null;
  triageStatus: RepositoryTriageStatus | null;
  analysisStatus: RepositoryAnalysisStatus | null;
  hasFailures: boolean;
  monetization: RepositoryMonetizationPotential | null;
  minStars: number | null;
  maxStars: number | null;
  starredOnly: boolean;
  sort: RepositoryCatalogSortBy;
  order: RepositoryCatalogSortOrder;
  visibleCount: number;
  totalCount: number;
  chips: RepositoryCatalogFilterChip[];
  isRefreshing: boolean;
  validationMessage: string | null;
  onSearchChange: (value: string) => void;
  onSourceChange: (value: RepositoryDiscoverySource | null) => void;
  onCategoryChange: (value: RepositoryCategory | null) => void;
  onAgentTagChange: (value: string | null) => void;
  onUserTagChange: (value: string | null) => void;
  onQueueStatusChange: (value: RepositoryQueueStatus | null) => void;
  onTriageStatusChange: (value: RepositoryTriageStatus | null) => void;
  onAnalysisStatusChange: (value: RepositoryAnalysisStatus | null) => void;
  onHasFailuresChange: (value: boolean) => void;
  onMonetizationChange: (value: RepositoryMonetizationPotential | null) => void;
  onMinStarsChange: (value: number | null) => void;
  onMaxStarsChange: (value: number | null) => void;
  onStarredOnlyChange: (value: boolean) => void;
  onSortChange: (value: RepositoryCatalogSortBy) => void;
  onOrderChange: (value: RepositoryCatalogSortOrder) => void;
  onRemoveChip: (key: RepositoryCatalogFilterChip["key"]) => void;
  onClearAll: () => void;
}) {
  const effectiveChips: RepositoryCatalogFilterChip[] =
    chips.length > 0
      ? chips
      : [
          ...(searchValue ? [{ key: "search" as const, label: `Search: ${searchValue}` }] : []),
          ...(source
            ? [
                {
                  key: "source" as const,
                  label: `Source: ${source.charAt(0).toUpperCase()}${source.slice(1)}`,
                },
              ]
            : []),
          ...(category
            ? [
                {
                  key: "category" as const,
                  label: `Category: ${CATEGORY_OPTIONS.find((option) => option.value === category)?.label ?? category}`,
                },
              ]
            : []),
          ...(agentTag ? [{ key: "agentTag" as const, label: `Agent Tag: ${agentTag}` }] : []),
          ...(userTag ? [{ key: "userTag" as const, label: `User Tag: ${userTag}` }] : []),
        ];

  return (
    <section className="card">
      <div className="card-header">
        <div>
          <p className="card-label">Corpus Browser</p>
          <h2 className="card-title" style={{ marginTop: "6px" }}>
            Search and curate repositories with real analysis tags
          </h2>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          {isRefreshing ? <span className="badge badge-blue">Refreshing</span> : null}
          <span className="card-label">
            Showing {visibleCount} of {totalCount} repos
          </span>
        </div>
      </div>

      <div className="repo-filter-grid repo-filter-grid-primary">
        <FilterInput
          ariaLabel="Search repositories"
          value={searchValue}
          placeholder="Search name or description"
          onChange={onSearchChange}
        />
        <FilterSelect
          ariaLabel="Discovery source"
          value={source ?? ""}
          options={SOURCE_OPTIONS}
          onChange={(value) => onSourceChange((value || null) as RepositoryDiscoverySource | null)}
        />
        <FilterSelect
          ariaLabel="Category"
          value={category ?? ""}
          options={CATEGORY_OPTIONS}
          onChange={(value) => onCategoryChange((value || null) as RepositoryCategory | null)}
        />
        <FilterSelect
          ariaLabel="Monetization fit"
          value={monetization ?? ""}
          options={MONETIZATION_OPTIONS}
          onChange={(value) =>
            onMonetizationChange((value || null) as RepositoryMonetizationPotential | null)
          }
        />
        <FilterSelect
          ariaLabel="Sort by"
          value={sort}
          options={SORT_OPTIONS}
          onChange={(value) => onSortChange(value as RepositoryCatalogSortBy)}
        />
      </div>

      <div className="repo-filter-grid" style={{ marginTop: "14px" }}>
        <FilterInput
          ariaLabel="Agent tag"
          value={agentTag ?? ""}
          placeholder="workflow, crm, analytics"
          onChange={(value) => onAgentTagChange(value.trim() ? value.trim().toLowerCase() : null)}
        />
        <FilterInput
          ariaLabel="User tag"
          value={userTag ?? ""}
          placeholder="high-priority, saas-candidate"
          onChange={(value) => onUserTagChange(value.trim() || null)}
        />
        <FilterSelect
          ariaLabel="Queue status"
          value={queueStatus ?? ""}
          options={QUEUE_OPTIONS}
          onChange={(value) => onQueueStatusChange((value || null) as RepositoryQueueStatus | null)}
        />
        <FilterSelect
          ariaLabel="Triage status"
          value={triageStatus ?? ""}
          options={TRIAGE_OPTIONS}
          onChange={(value) => onTriageStatusChange((value || null) as RepositoryTriageStatus | null)}
        />
        <FilterSelect
          ariaLabel="Analysis status"
          value={analysisStatus ?? ""}
          options={ANALYSIS_OPTIONS}
          onChange={(value) =>
            onAnalysisStatusChange((value || null) as RepositoryAnalysisStatus | null)
          }
        />
      </div>

      <div className="repo-filter-toolbar">
        <label className="repo-filter-control compact">
          <span className="repo-filter-label">Minimum stars</span>
          <input
            aria-label="Minimum stars"
            className="input"
            min={0}
            placeholder="No threshold"
            type="number"
            value={minStars ?? ""}
            onChange={(event) => {
              const value = event.target.value;
              onMinStarsChange(value === "" ? null : Number.parseInt(value, 10));
            }}
          />
        </label>
        <label className="repo-filter-control compact">
          <span className="repo-filter-label">Maximum stars</span>
          <input
            aria-label="Maximum stars"
            className="input"
            min={0}
            placeholder="No ceiling"
            type="number"
            value={maxStars ?? ""}
            onChange={(event) => {
              const value = event.target.value;
              onMaxStarsChange(value === "" ? null : Number.parseInt(value, 10));
            }}
          />
        </label>
        <label className="repo-filter-toggle">
          <input
            aria-label="Show failures only"
            checked={hasFailures}
            type="checkbox"
            onChange={(event) => onHasFailuresChange(event.target.checked)}
          />
          <span>Show failures only</span>
        </label>
        <label className="repo-filter-toggle">
          <input
            aria-label="Show starred only"
            checked={starredOnly}
            type="checkbox"
            onChange={(event) => onStarredOnlyChange(event.target.checked)}
          />
          <span>Show watchlist only</span>
        </label>
        <button
          aria-label="Toggle sort order"
          className="btn"
          style={{ minHeight: "36px", alignSelf: "end" }}
          type="button"
          onClick={() => onOrderChange(order === "desc" ? "asc" : "desc")}
        >
          {order === "desc" ? "Descending" : "Ascending"}
        </button>
      </div>

      <div className="repo-chip-row">
        <span className="card-label">Filters</span>
        {effectiveChips.length > 0 ? (
          <>
            {effectiveChips.map((chip) => (
              <button
                key={chip.key}
                aria-label={`Remove ${chip.label} filter`}
                className="tag tag-user"
                type="button"
                onClick={() => onRemoveChip(chip.key)}
              >
                {chip.label} ×
              </button>
            ))}
            <button aria-label="Clear all" className="btn btn-sm" type="button" onClick={onClearAll}>
              Clear filters
            </button>
          </>
        ) : (
          <span style={{ color: "var(--text-2)", fontSize: "12px" }}>No active filters</span>
        )}
      </div>

      {validationMessage ? (
        <div className="card" style={{ marginTop: "14px", borderColor: "rgba(217, 79, 79, 0.28)", background: "var(--red-dim)" }}>
          <p className="card-label" style={{ color: "var(--red)" }}>
            Validation Issue
          </p>
          <p style={{ marginTop: "8px", color: "var(--text-1)" }}>{validationMessage}</p>
        </div>
      ) : null}
    </section>
  );
}

import type { RepositoryCatalogItem } from "@/api/repositories";

function formatCategory(value: RepositoryCatalogItem["category"]): string {
  if (!value) {
    return "—";
  }
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatToken(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function renderTagList(tags: string[], className: string, emptyLabel = "—") {
  if (tags.length === 0) {
    return <span style={{ color: "var(--text-3)" }}>{emptyLabel}</span>;
  }
  return (
    <div className="repo-tag-cluster">
      {tags.map((tag) => (
        <span key={tag} className={className}>
          {tag}
        </span>
      ))}
    </div>
  );
}

function getFitClass(fit: string | null): string {
  if (fit === "high") {
    return "tag tag-green";
  }
  if (fit === "medium") {
    return "tag tag-yellow";
  }
  if (fit === "low") {
    return "tag tag-red";
  }
  return "tag";
}

function getSourceClass(source: string): string {
  return source === "backfill" ? "tag tag-blue" : "tag tag-active";
}

function getStatusClass(status: string): string {
  if (status === "accepted" || status === "completed") {
    return "tag tag-green";
  }
  if (status === "failed" || status === "rejected") {
    return "tag tag-red";
  }
  if (status === "in_progress" || status === "pending") {
    return "tag tag-yellow";
  }
  return "tag";
}

interface Props {
  items: RepositoryCatalogItem[];
  selectedIds?: Set<number>;
  onToggleSelection?: (id: number) => void;
  onToggleStar: (id: number, starred: boolean) => void;
  togglingRepositoryId: number | null;
  onRowClick: (id: number) => void;
}

export function RepositoryCatalogTable({
  items,
  selectedIds = new Set<number>(),
  onToggleSelection,
  onToggleStar,
  togglingRepositoryId,
  onRowClick,
}: Props) {
  const allSelected =
    items.length > 0 &&
    items.every((item) => selectedIds.has(item.github_repository_id));

  return (
    <div className="repo-table-shell">
      <table className="tbl repo-table repo-table-compact">
        <thead>
          <tr>
            <th style={{ width: "40px" }}>
              <input
                aria-label="Select all repositories"
                checked={allSelected}
                type="checkbox"
                onChange={() => {
                  if (!onToggleSelection) {
                    return;
                  }
                  if (allSelected) {
                    items.forEach((item) => {
                      if (selectedIds.has(item.github_repository_id)) {
                        onToggleSelection(item.github_repository_id);
                      }
                    });
                    return;
                  }
                  items.forEach((item) => {
                    if (!selectedIds.has(item.github_repository_id)) {
                      onToggleSelection(item.github_repository_id);
                    }
                  });
                }}
              />
            </th>
            <th>Repository</th>
            <th>Category</th>
            <th>Fit</th>
            <th style={{ textAlign: "right" }}>Stars</th>
            <th>Source</th>
            <th>Agent Tags</th>
            <th>User Tags</th>
            <th>Triage</th>
            <th>Analysis</th>
            <th style={{ width: "52px", textAlign: "center" }}>★</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const isSelected = selectedIds.has(item.github_repository_id);
            return (
              <tr
                key={item.github_repository_id}
                className={isSelected ? "selected" : ""}
                style={{ cursor: "pointer" }}
                onClick={() => onRowClick(item.github_repository_id)}
              >
                <td onClick={(event) => event.stopPropagation()}>
                  <input
                    aria-label={`Select ${item.full_name}`}
                    checked={isSelected}
                    type="checkbox"
                    onChange={() => onToggleSelection?.(item.github_repository_id)}
                  />
                </td>
                <td className="repo-table-name">
                  <div className="repo-table-name-stack">
                    <span className="repo-table-title">{item.full_name}</span>
                    <span className="repo-table-subtitle">
                      {item.repository_description || "No repository description provided."}
                    </span>
                  </div>
                </td>
                <td>
                  {item.category ? (
                    <span className="tag">{formatCategory(item.category)}</span>
                  ) : (
                    <span style={{ color: "var(--text-3)" }}>—</span>
                  )}
                </td>
                <td>
                  <span className={getFitClass(item.monetization_potential)}>
                    {formatToken(item.monetization_potential ?? "unscored")}
                  </span>
                </td>
                <td className="repo-table-number-cell">
                  {item.stargazers_count.toLocaleString()}
                </td>
                <td>
                  <span className={getSourceClass(item.discovery_source)}>
                    {formatToken(item.discovery_source)}
                  </span>
                </td>
                <td>{renderTagList(item.agent_tags ?? [], "tag tag-agent")}</td>
                <td>{renderTagList(item.user_tags, "tag tag-user")}</td>
                <td>
                  <span className={getStatusClass(item.triage_status)}>
                    {formatToken(item.triage_status)}
                  </span>
                </td>
                <td>
                  <span className={getStatusClass(item.analysis_status)}>
                    {formatToken(item.analysis_status)}
                  </span>
                </td>
                <td onClick={(event) => event.stopPropagation()} style={{ textAlign: "center" }}>
                  <button
                    aria-label={item.is_starred ? "Unstar repository" : "Star repository"}
                    aria-pressed={item.is_starred}
                    className={`repo-star-button ${item.is_starred ? "active" : ""}`}
                    disabled={togglingRepositoryId === item.github_repository_id}
                    type="button"
                    onClick={() => onToggleStar(item.github_repository_id, !item.is_starred)}
                  >
                    {item.is_starred ? "★" : "☆"}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

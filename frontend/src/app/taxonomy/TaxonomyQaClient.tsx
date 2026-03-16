"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { startTransition, useMemo } from "react";

import {
  fetchRepositoryCatalog,
  getRepositoryCatalogQueryKey,
  type RepositoryCatalogItem,
  type RepositoryCatalogViewState,
} from "@/api/repositories";
import { CatalogPagination } from "@/components/repositories/CatalogPagination";
import { formatAppDateTime } from "@/lib/time";

type QaBucket =
  | "needs-review"
  | "low-confidence"
  | "no-category"
  | "no-tags"
  | "suggested-tags"
  | "healthy";

const DEFAULT_BUCKET: QaBucket = "needs-review";
const PAGE_SIZE_OPTIONS = [30, 50, 100] as const;

function parsePositiveInt(value: string | null, fallback: number): number {
  if (!value) {
    return fallback;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseBucket(value: string | null): QaBucket {
  switch (value) {
    case "low-confidence":
    case "no-category":
    case "no-tags":
    case "suggested-tags":
    case "healthy":
      return value;
    default:
      return DEFAULT_BUCKET;
  }
}

function buildTaxonomyUrl(page: number, pageSize: number, bucket: QaBucket): string {
  const params = new URLSearchParams();
  if (page !== 1) {
    params.set("page", String(page));
  }
  if (pageSize !== 50) {
    params.set("pageSize", String(pageSize));
  }
  if (bucket !== DEFAULT_BUCKET) {
    params.set("bucket", bucket);
  }
  const query = params.toString();
  return query.length > 0 ? `/taxonomy?${query}` : "/taxonomy";
}

function getBaseCatalogState(page: number, pageSize: number): RepositoryCatalogViewState {
  return {
    page,
    pageSize,
    sort: "ingested_at",
    order: "desc",
    search: null,
    source: null,
    queueStatus: null,
    triageStatus: "accepted",
    analysisStatus: "completed",
    hasFailures: false,
    category: null,
    agentTag: null,
    userTag: null,
    monetization: null,
    minStars: null,
    maxStars: null,
    starredOnly: false,
    ideaFamilyId: null,
  };
}

function isLowConfidence(item: RepositoryCatalogItem): boolean {
  const overall = item.confidence_score ?? 0;
  const category = item.category_confidence_score ?? 0;
  return overall < 70 || category < 70;
}

function getQaIssues(item: RepositoryCatalogItem): string[] {
  const issues: string[] = [];
  if (!item.category) {
    issues.push("No category");
  }
  if ((item.agent_tags ?? []).length === 0) {
    issues.push("No agent tags");
  }
  if (isLowConfidence(item)) {
    issues.push("Low confidence");
  }
  if ((item.suggested_new_tags ?? []).length > 0) {
    issues.push("Suggested tags need review");
  }
  if (item.analysis_outcome && item.analysis_outcome !== "completed") {
    issues.push(item.analysis_outcome.replaceAll("_", " "));
  }
  return issues;
}

function matchesBucket(item: RepositoryCatalogItem, bucket: QaBucket): boolean {
  if (bucket === "low-confidence") {
    return isLowConfidence(item);
  }
  if (bucket === "no-category") {
    return !item.category;
  }
  if (bucket === "no-tags") {
    return (item.agent_tags ?? []).length === 0;
  }
  if (bucket === "suggested-tags") {
    return (item.suggested_new_tags ?? []).length > 0;
  }
  if (bucket === "healthy") {
    return getQaIssues(item).length === 0;
  }
  return getQaIssues(item).length > 0;
}

function formatPercent(value: number | null | undefined): string {
  if (value == null) {
    return "Unknown";
  }
  return `${value}%`;
}

function bucketTitle(bucket: QaBucket): string {
  switch (bucket) {
    case "low-confidence":
      return "Low Confidence";
    case "no-category":
      return "No Category";
    case "no-tags":
      return "No Agent Tags";
    case "suggested-tags":
      return "Suggested Tags";
    case "healthy":
      return "Looks Healthy";
    default:
      return "Needs Review";
  }
}

function bucketDescription(bucket: QaBucket): string {
  switch (bucket) {
    case "low-confidence":
      return "Analyses with weak overall or category confidence.";
    case "no-category":
      return "Completed analyses that still do not have a canonical category.";
    case "no-tags":
      return "Completed analyses missing normalized agent tags.";
    case "suggested-tags":
      return "Repos whose analysis suggested tags outside the current canonical set.";
    case "healthy":
      return "Completed analyses on this page without obvious taxonomy warnings.";
    default:
      return "The review queue for suspicious, incomplete, or drift-prone Analyst results.";
  }
}

export function TaxonomyQaClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const page = parsePositiveInt(searchParams.get("page"), 1);
  const pageSize = Math.min(100, parsePositiveInt(searchParams.get("pageSize"), 50));
  const bucket = parseBucket(searchParams.get("bucket"));
  const catalogState = useMemo(() => getBaseCatalogState(page, pageSize), [page, pageSize]);

  const catalogQuery = useQuery({
    queryKey: [...getRepositoryCatalogQueryKey(catalogState), "taxonomy-qa"],
    queryFn: () => fetchRepositoryCatalog(catalogState),
    placeholderData: keepPreviousData,
  });

  const items = catalogQuery.data?.items ?? [];
  const filteredItems = useMemo(
    () => items.filter((item) => matchesBucket(item, bucket)),
    [bucket, items],
  );
  const counts = useMemo(() => {
    const summary = {
      "needs-review": 0,
      "low-confidence": 0,
      "no-category": 0,
      "no-tags": 0,
      "suggested-tags": 0,
      healthy: 0,
    } satisfies Record<QaBucket, number>;

    for (const item of items) {
      if (matchesBucket(item, "needs-review")) {
        summary["needs-review"] += 1;
      }
      if (matchesBucket(item, "low-confidence")) {
        summary["low-confidence"] += 1;
      }
      if (matchesBucket(item, "no-category")) {
        summary["no-category"] += 1;
      }
      if (matchesBucket(item, "no-tags")) {
        summary["no-tags"] += 1;
      }
      if (matchesBucket(item, "suggested-tags")) {
        summary["suggested-tags"] += 1;
      }
      if (matchesBucket(item, "healthy")) {
        summary.healthy += 1;
      }
    }

    return summary;
  }, [items]);

  const updateRoute = (next: { page?: number; pageSize?: number; bucket?: QaBucket }) => {
    const nextPage = next.page ?? page;
    const nextPageSize = next.pageSize ?? pageSize;
    const nextBucket = next.bucket ?? bucket;
    startTransition(() => {
      router.replace(buildTaxonomyUrl(nextPage, nextPageSize, nextBucket), { scroll: false });
    });
  };

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Taxonomy QA</span>
        <span className="topbar-breadcrumb">analyst quality control</span>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "20px" }}>
        <div className="hero-strip mb-16">
          <div>
            <h2>Review Analyst Accuracy</h2>
            <div className="sub">
              Inspect completed analyses for category drift, weak confidence, and missing tags.
            </div>
          </div>
          <div className="flex items-center gap-12" style={{ flexWrap: "wrap" }}>
            <span className="badge badge-blue">
              Reviewing latest {pageSize} completed analyses
            </span>
            <Link className="btn" href="/repositories">
              Open Repository Catalog
            </Link>
          </div>
        </div>

        <div className="grid g4 mb-16">
          <div className="card metric-card">
            <div className="card-label">Loaded Page</div>
            <div className="card-metric">{items.length}</div>
            <div className="card-sub">
              Page {catalogQuery.data?.page ?? page} of {catalogQuery.data?.total_pages ?? 0}
            </div>
          </div>
          <div className="card metric-card">
            <div className="card-label">Needs Review</div>
            <div className="card-metric">{counts["needs-review"]}</div>
            <div className="card-sub">On this loaded page of completed analyses</div>
          </div>
          <div className="card metric-card">
            <div className="card-label">Suggested Tags</div>
            <div className="card-metric">{counts["suggested-tags"]}</div>
            <div className="card-sub">Potential canonical taxonomy gaps</div>
          </div>
          <div className="card metric-card">
            <div className="card-label">Looks Healthy</div>
            <div className="card-metric">{counts.healthy}</div>
            <div className="card-sub">No obvious taxonomy warning flags on this page</div>
          </div>
        </div>

        <div className="card mb-16">
          <div className="section-head" style={{ marginTop: 0, marginBottom: "14px" }}>
            <span className="section-title">Review Buckets</span>
            <div className="section-line" />
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
            {(
              [
                "needs-review",
                "low-confidence",
                "no-category",
                "no-tags",
                "suggested-tags",
                "healthy",
              ] as QaBucket[]
            ).map((value) => (
              <button
                key={value}
                className={`btn btn-sm ${bucket === value ? "btn-primary" : ""}`}
                type="button"
                onClick={() => updateRoute({ page: 1, bucket: value })}
              >
                {bucketTitle(value)} ({counts[value]})
              </button>
            ))}
          </div>
          <p style={{ marginTop: "14px", color: "var(--text-2)", fontSize: "13px" }}>
            {bucketDescription(bucket)}
          </p>
          <p style={{ marginTop: "8px", color: "var(--text-3)", fontSize: "12px" }}>
            Counts reflect the current loaded page, sorted by newest repos added to the website.
          </p>
        </div>

        <div className="repo-table-shell">
          <table className="repo-table repo-table-compact">
            <thead>
              <tr>
                <th className="repo-table-name">Repository</th>
                <th>Issues</th>
                <th>Category</th>
                <th>Scores</th>
                <th>Agent Tags</th>
                <th>Suggested Tags</th>
                <th>Outcome</th>
                <th>Added</th>
              </tr>
            </thead>
            <tbody>
              {catalogQuery.isLoading ? (
                <tr>
                  <td colSpan={8} style={{ padding: "24px", color: "var(--text-3)" }}>
                    Loading taxonomy review queue...
                  </td>
                </tr>
              ) : null}
              {catalogQuery.isError ? (
                <tr>
                  <td colSpan={8} style={{ padding: "24px", color: "var(--red)" }}>
                    Failed to load taxonomy QA data.
                  </td>
                </tr>
              ) : null}
              {!catalogQuery.isLoading && !catalogQuery.isError && filteredItems.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ padding: "24px", color: "var(--text-3)" }}>
                    No repositories on this page match the current review bucket.
                  </td>
                </tr>
              ) : null}
              {!catalogQuery.isLoading &&
                !catalogQuery.isError &&
                filteredItems.map((item) => {
                  const issues = getQaIssues(item);
                  return (
                    <tr key={item.github_repository_id}>
                      <td className="repo-table-name">
                        <div className="repo-table-name-stack">
                          <Link
                            className="repo-table-title"
                            href={`/repositories/${item.github_repository_id}`}
                          >
                            {item.full_name}
                          </Link>
                          <div className="repo-table-subtitle">
                            {item.repository_description ?? "No repository description."}
                          </div>
                          <div className="repo-tag-cluster">
                            {item.is_starred ? <span className="badge badge-yellow">Favorite</span> : null}
                            {item.monetization_potential ? (
                              <span className="badge badge-purple">
                                {item.monetization_potential} monetization
                              </span>
                            ) : null}
                          </div>
                        </div>
                      </td>
                      <td>
                        <div className="repo-tag-cluster">
                          {issues.length > 0 ? (
                            issues.map((issue) => (
                              <span key={issue} className="badge badge-red">
                                {issue}
                              </span>
                            ))
                          ) : (
                            <span className="badge badge-green">No obvious issues</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                          <span style={{ color: "var(--text-0)", fontWeight: 600 }}>
                            {item.category ?? "Uncategorized"}
                          </span>
                          <span style={{ color: "var(--text-3)", fontSize: "12px" }}>
                            Category confidence: {formatPercent(item.category_confidence_score)}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                          <span style={{ color: "var(--text-0)", fontWeight: 600 }}>
                            Overall {formatPercent(item.confidence_score)}
                          </span>
                          <span style={{ color: "var(--text-3)", fontSize: "12px" }}>
                            Stars {item.stargazers_count.toLocaleString()} · Forks {item.forks_count.toLocaleString()}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div className="repo-tag-cluster">
                          {(item.agent_tags ?? []).length > 0 ? (
                            (item.agent_tags ?? []).map((tag) => (
                              <span key={tag} className="badge badge-blue">
                                {tag}
                              </span>
                            ))
                          ) : (
                            <span className="badge badge-muted">Missing</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <div className="repo-tag-cluster">
                          {(item.suggested_new_tags ?? []).length > 0 ? (
                            (item.suggested_new_tags ?? []).map((tag) => (
                              <span key={tag} className="badge badge-yellow">
                                {tag}
                              </span>
                            ))
                          ) : (
                            <span className="badge badge-muted">None</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                          <span className="badge badge-muted">
                            {(item.analysis_outcome ?? "completed").replaceAll("_", " ")}
                          </span>
                          <span style={{ color: "var(--text-3)", fontSize: "12px" }}>
                            {item.has_analysis_artifact ? "Analysis artifact saved" : "No analysis artifact"}
                          </span>
                        </div>
                      </td>
                      <td style={{ whiteSpace: "nowrap", color: "var(--text-2)", fontSize: "12px" }}>
                        {formatAppDateTime(item.queue_created_at)}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>

        <div style={{ marginTop: "16px" }}>
          <CatalogPagination
            page={page}
            totalPages={catalogQuery.data?.total_pages ?? 0}
            pageSize={PAGE_SIZE_OPTIONS.includes(pageSize as (typeof PAGE_SIZE_OPTIONS)[number]) ? pageSize : 50}
            totalCount={catalogQuery.data?.total ?? 0}
            onPageChange={(nextPage) => updateRoute({ page: nextPage })}
            onPageSizeChange={(nextPageSize) => updateRoute({ page: 1, pageSize: nextPageSize })}
          />
        </div>
      </div>
    </>
  );
}

"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo } from "react";

import {
  fetchRepositoryCatalog,
  getRepositoryCatalogQueryKey,
  type RepositoryCatalogItem,
  type RepositoryCatalogViewState,
} from "@/api/repositories";
import { formatRelativeTimestamp } from "@/components/agents/agentPresentation";

const ACCEPTED_PENDING_ANALYSIS_VIEW: RepositoryCatalogViewState = {
  page: 1,
  pageSize: 6,
  sort: "ingested_at",
  order: "desc",
  search: null,
  source: null,
  queueStatus: null,
  triageStatus: "accepted",
  analysisStatus: "pending",
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

function formatSourceLabel(source: RepositoryCatalogItem["discovery_source"]): string {
  if (source === "backfill") {
    return "Backfill";
  }
  if (source === "firehose") {
    return "Firehose";
  }
  return "Unknown";
}

export function AcceptedAnalysisQueuePanel({
  pendingCount,
  title = "Accepted Waiting For Analyst",
}: {
  pendingCount: number;
  title?: string;
}) {
  const viewState = useMemo(() => ACCEPTED_PENDING_ANALYSIS_VIEW, []);
  const queueQuery = useQuery({
    queryKey: [...getRepositoryCatalogQueryKey(viewState), "accepted-pending-analysis-panel"],
    queryFn: () => fetchRepositoryCatalog(viewState),
    staleTime: 15_000,
    refetchInterval: 15_000,
  });

  return (
    <section className="card">
      <div className="card-header" style={{ alignItems: "flex-start", gap: "12px" }}>
        <div>
          <h2 className="card-title" style={{ fontSize: "18px" }}>
            {title}
          </h2>
          <p style={{ marginTop: "6px", color: "var(--text-2)" }}>
            Repaired and newly accepted repos land here before README capture and analysis finish.
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", justifyContent: "flex-end" }}>
          <span className="badge badge-blue">
            {pendingCount.toLocaleString()} waiting
          </span>
          <Link
            className="btn btn-sm"
            href="/repositories?triage_status=accepted&analysis_status=pending&sort_by=ingested_at&sort_order=desc"
          >
            Open Filtered Repos
          </Link>
        </div>
      </div>

      {queueQuery.isLoading ? (
        <div style={{ color: "var(--text-2)" }}>Loading accepted Analyst queue…</div>
      ) : queueQuery.isError ? (
        <div style={{ color: "var(--red)" }}>
          Could not load the accepted Analyst queue sample.
        </div>
      ) : queueQuery.data && queueQuery.data.items.length > 0 ? (
        <div style={{ display: "grid", gap: "10px" }}>
          {queueQuery.data.items.map((repo) => (
            <Link
              key={repo.github_repository_id}
              href={`/repositories/${repo.github_repository_id}`}
              className="card"
              style={{
                padding: "12px",
                background: "var(--bg-3)",
                borderColor: "var(--border)",
                textDecoration: "none",
                color: "inherit",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "12px",
                  alignItems: "flex-start",
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600, color: "var(--text-0)" }}>{repo.full_name}</div>
                  <div
                    style={{
                      marginTop: "4px",
                      color: "var(--text-2)",
                      fontSize: "13px",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                    }}
                  >
                    {repo.repository_description ?? "No repository description captured."}
                  </div>
                </div>
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", justifyContent: "flex-end" }}>
                  <span className="badge badge-green">{formatSourceLabel(repo.discovery_source)}</span>
                  <span className="badge badge-muted">{repo.stargazers_count.toLocaleString()} stars</span>
                </div>
              </div>

              <div
                style={{
                  marginTop: "8px",
                  display: "flex",
                  gap: "12px",
                  flexWrap: "wrap",
                  color: "var(--text-2)",
                  fontSize: "12px",
                }}
              >
                <span>Added {formatRelativeTimestamp(repo.queue_created_at)}</span>
                <span>Analysis {repo.analysis_status}</span>
                <span>Triage {repo.triage_status}</span>
              </div>
            </Link>
          ))}
          {queueQuery.data.total > queueQuery.data.items.length ? (
            <div style={{ color: "var(--text-2)", fontSize: "12px" }}>
              Showing the newest {queueQuery.data.items.length} of {queueQuery.data.total.toLocaleString()} repos waiting for Analyst.
            </div>
          ) : null}
        </div>
      ) : (
        <div style={{ color: "var(--text-2)" }}>
          No accepted repos are waiting for Analyst right now.
        </div>
      )}
    </section>
  );
}

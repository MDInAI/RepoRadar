"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  addRepositoryUserTag,
  fetchRepositoryDetail,
  getRepositoryDetailQueryKey,
  removeRepositoryUserTag,
  updateRepositoryStar,
  type RepositoryDetailResponse,
} from "@/api/repositories";

type RepositoryTab = "overview" | "readme" | "analysis" | "history";
type RepositoryActionKey = "family-assignment" | "combiner-draft" | "similar-project-scan";

interface RepositoryActionDefinition {
  key: RepositoryActionKey;
  title: string;
  destination: string;
  expectedResult: string;
  buttonLabel: string;
}

const TABS: Array<{ key: RepositoryTab; label: string }> = [
  { key: "overview", label: "Overview" },
  { key: "readme", label: "README Intelligence" },
  { key: "analysis", label: "Analyst Output" },
  { key: "history", label: "History" },
];

const ACTIONS: RepositoryActionDefinition[] = [
  {
    key: "family-assignment",
    title: "Add to Family",
    destination: "Ideas > Family Workspace",
    expectedResult: "The repository is staged for a future family clustering decision.",
    buttonLabel: "Stage family assignment",
  },
  {
    key: "combiner-draft",
    title: "Create Combiner Brief",
    destination: "Ideas > Combiner Results",
    expectedResult: "A synthesis prompt is prepared for idea-family generation.",
    buttonLabel: "Create Combiner brief",
  },
  {
    key: "similar-project-scan",
    title: "Similar-Project Scan",
    destination: "Repositories > Similar Results",
    expectedResult: "A follow-up scan is queued for comparable repositories.",
    buttonLabel: "Queue similar-project scan",
  },
];

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown";
  }
  return `${parsed.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function formatRelativeDate(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown";
  }
  const diffHours = Math.round((Date.now() - parsed.getTime()) / (1000 * 60 * 60));
  if (diffHours < 1) {
    return "Less than 1 hour ago";
  }
  if (diffHours < 24) {
    return `${diffHours} hour${diffHours === 1 ? "" : "s"} ago`;
  }
  const diffDays = Math.round(diffHours / 24);
  return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;
}

function titleCase(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function renderTagList(tags: string[], className: string, emptyLabel = "None yet") {
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

function buildDecisionRows(detail: RepositoryDetailResponse) {
  const fit = titleCase(detail.analysis_summary?.monetization_potential ?? "unscored");
  const category = detail.category ? titleCase(detail.category) : "Unclassified";
  const recommendation =
    detail.analysis_summary?.monetization_potential === "high"
      ? "Create family + Combiner brief"
      : detail.analysis_summary?.monetization_potential === "medium"
        ? "Keep on watchlist and gather more evidence"
        : "Monitor only";

  return [
    { label: "Monetization", value: `${fit} fit` },
    { label: "Category", value: category },
    {
      label: "Market timing",
      value:
        detail.stargazers_count >= 1000
          ? "Strong community signal"
          : "Needs more demand validation",
    },
    { label: "Recommended action", value: recommendation },
  ];
}

function buildHistoryRows(detail: RepositoryDetailResponse) {
  return [
    ["Discovered", formatTimestamp(detail.discovered_at)],
    ["Status updated", formatTimestamp(detail.status_updated_at)],
    ["Triage completed", formatTimestamp(detail.triage.triaged_at)],
    ["Analysis started", formatTimestamp(detail.processing.analysis_started_at)],
    ["Analysis completed", formatTimestamp(detail.processing.analysis_completed_at)],
    ["Last attempted", formatTimestamp(detail.processing.analysis_last_attempted_at)],
  ];
}

function buildCategorySignals(detail: RepositoryDetailResponse): string[] {
  const signals = new Set<string>();
  if (detail.category) {
    signals.add(titleCase(detail.category));
  }
  if (detail.discovery_source) {
    signals.add(titleCase(detail.discovery_source));
  }
  if (detail.analysis_summary?.monetization_potential) {
    signals.add(`${titleCase(detail.analysis_summary.monetization_potential)} fit`);
  }
  return [...signals];
}

export function RepositoryDetailClient({ repositoryId }: { repositoryId: number }) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<RepositoryTab>("overview");
  const [selectedAction, setSelectedAction] = useState<RepositoryActionDefinition | null>(null);
  const [newUserTag, setNewUserTag] = useState("");
  const [curationError, setCurationError] = useState<string | null>(null);

  const detailQuery = useQuery({
    queryKey: getRepositoryDetailQueryKey(repositoryId),
    queryFn: () => fetchRepositoryDetail(repositoryId),
  });

  const starMutation = useMutation({
    mutationFn: (starred: boolean) => updateRepositoryStar(repositoryId, starred),
    onMutate: async (starred) => {
      setCurationError(null);
      await queryClient.cancelQueries({ queryKey: getRepositoryDetailQueryKey(repositoryId) });
      const previousDetail = queryClient.getQueryData<RepositoryDetailResponse>(
        getRepositoryDetailQueryKey(repositoryId),
      );
      queryClient.setQueryData<RepositoryDetailResponse>(
        getRepositoryDetailQueryKey(repositoryId),
        (current) => (current ? { ...current, is_starred: starred } : current),
      );
      return { previousDetail };
    },
    onError: (error, _starred, context) => {
      if (context?.previousDetail) {
        queryClient.setQueryData(getRepositoryDetailQueryKey(repositoryId), context.previousDetail);
      }
      setCurationError(error instanceof Error ? error.message : "Unable to update watch state.");
    },
    onSuccess: (curation) => {
      queryClient.setQueryData<RepositoryDetailResponse>(
        getRepositoryDetailQueryKey(repositoryId),
        (current) =>
          current
            ? {
                ...current,
                is_starred: curation.is_starred,
                user_tags: curation.user_tags,
              }
            : current,
      );
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["repositories", "catalog"] });
    },
  });

  const addTagMutation = useMutation({
    mutationFn: (tagLabel: string) => addRepositoryUserTag(repositoryId, tagLabel),
    onMutate: () => setCurationError(null),
    onError: (error) => {
      setCurationError(error instanceof Error ? error.message : "Unable to add user tag.");
    },
    onSuccess: (tag) => {
      setNewUserTag("");
      queryClient.setQueryData<RepositoryDetailResponse>(
        getRepositoryDetailQueryKey(repositoryId),
        (current) =>
          current
            ? {
                ...current,
                user_tags: [...current.user_tags, tag.tag_label],
              }
            : current,
      );
      void queryClient.invalidateQueries({ queryKey: ["repositories", "catalog"] });
    },
  });

  const removeTagMutation = useMutation({
    mutationFn: (tagLabel: string) => removeRepositoryUserTag(repositoryId, tagLabel),
    onMutate: () => setCurationError(null),
    onError: (error) => {
      setCurationError(error instanceof Error ? error.message : "Unable to remove user tag.");
    },
    onSuccess: (_result, tagLabel) => {
      queryClient.setQueryData<RepositoryDetailResponse>(
        getRepositoryDetailQueryKey(repositoryId),
        (current) =>
          current
            ? {
                ...current,
                user_tags: current.user_tags.filter((tag) => tag !== tagLabel),
              }
            : current,
      );
      void queryClient.invalidateQueries({ queryKey: ["repositories", "catalog"] });
    },
  });

  const detail = detailQuery.data;
  const decisionRows = useMemo(() => (detail ? buildDecisionRows(detail) : []), [detail]);
  const historyRows = useMemo(() => (detail ? buildHistoryRows(detail) : []), [detail]);
  const categorySignals = useMemo(() => (detail ? buildCategorySignals(detail) : []), [detail]);

  if (!Number.isFinite(repositoryId) || repositoryId <= 0) {
    return (
      <main className="repo-detail-page">
        <section className="card">
          <p className="card-label">Invalid Route</p>
          <h1 className="card-title" style={{ marginTop: "10px", fontSize: "22px" }}>
            Repository ID is missing or invalid
          </h1>
          <p style={{ marginTop: "10px", color: "var(--text-2)" }}>
            Open the dossier from the repositories catalog so the route can resolve a valid
            repository identifier.
          </p>
        </section>
      </main>
    );
  }

  if (detailQuery.isLoading && !detail) {
    return (
      <main className="repo-detail-page">
        <section className="card">
          <p className="card-label">Loading</p>
          <h1 className="card-title" style={{ marginTop: "10px", fontSize: "22px" }}>
            Hydrating repository dossier
          </h1>
          <p style={{ marginTop: "10px", color: "var(--text-2)" }}>
            Pulling README context, triage rationale, analysis output, and curation state into the
            dossier workspace.
          </p>
        </section>
      </main>
    );
  }

  if (detailQuery.isError || !detail) {
    return (
      <main className="repo-detail-page">
        <section className="card" style={{ borderColor: "rgba(217, 79, 79, 0.28)", background: "var(--red-dim)" }}>
          <p className="card-label" style={{ color: "var(--red)" }}>
            Dossier Error
          </p>
          <h1 className="card-title" style={{ marginTop: "10px", fontSize: "22px" }}>
            Unable to load repository detail
          </h1>
          <p style={{ marginTop: "10px", color: "var(--text-1)" }}>
            {detailQuery.error instanceof Error
              ? detailQuery.error.message
              : "The repository dossier could not be loaded."}
          </p>
        </section>
      </main>
    );
  }

  const failureContext = detail.processing.failure;

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Repository Detail</span>
        <span className="topbar-breadcrumb">dossier · {detail.repository_name}</span>
      </div>

      <main className="repo-detail-page">
        <section className="hero-strip">
          <div style={{ minWidth: 0 }}>
            <p className="card-label">Repository Dossier</p>
            <h1 style={{ marginTop: "10px", fontSize: "28px", fontWeight: 700, letterSpacing: "-0.04em" }}>
              {detail.full_name}
            </h1>
            <p style={{ marginTop: "10px", color: "var(--text-2)", maxWidth: "780px", fontSize: "15px" }}>
              {detail.repository_description || "No description is stored for this repository yet."}
            </p>
            <div className="repo-hero-metrics">
              <span>{detail.stargazers_count.toLocaleString()} stars</span>
              <span>{detail.forks_count.toLocaleString()} forks</span>
              <span>Discovered {formatRelativeDate(detail.discovered_at)}</span>
              <span>Last commit: {formatRelativeDate(detail.pushed_at)}</span>
            </div>
          </div>

          <div className="repo-hero-badges">
            <button
              aria-label={detail.is_starred ? "Unstar repository" : "Star repository"}
              className={`btn ${detail.is_starred ? "btn-primary" : ""}`}
              type="button"
              onClick={() => starMutation.mutate(!detail.is_starred)}
            >
              {detail.is_starred ? "★ Watchlisted" : "☆ Watchlist"}
            </button>
            <span className="badge badge-green">{titleCase(detail.analysis_status)}</span>
            <span className="badge badge-blue">{titleCase(detail.discovery_source)}</span>
            {detail.analysis_summary?.monetization_potential ? (
              <span className="badge badge-yellow">
                {titleCase(detail.analysis_summary.monetization_potential)} Fit
              </span>
            ) : null}
          </div>
        </section>

        <div className="repo-tabs">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              className={`repo-tab ${tab.key === activeTab ? "active" : ""}`}
              type="button"
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="repo-dossier-grid">
          <div className="repo-dossier-main">
            {activeTab === "overview" ? (
              <>
                <section className="card">
                  <div className="card-header">
                    <div>
                      <h2 className="card-title" style={{ fontSize: "18px" }}>
                        Analyst Summary
                      </h2>
                    </div>
                    {detail.analysis_summary?.monetization_potential ? (
                      <span className="badge badge-green">
                        {titleCase(detail.analysis_summary.monetization_potential)} Confidence
                      </span>
                    ) : null}
                  </div>
                  <p style={{ color: "var(--text-1)", fontSize: "15px", lineHeight: 1.7 }}>
                    {detail.analysis_summary?.pros?.length
                      ? detail.analysis_summary.pros.join(" ")
                      : "Analysis output is not available yet. Once Analyst completes, this card will summarize fit, product signals, and gaps."}
                  </p>
                </section>

                <section className="card">
                  <div className="card-header">
                    <h2 className="card-title" style={{ fontSize: "18px" }}>
                      Decision Summary
                    </h2>
                  </div>
                  <div className="repo-key-value-list">
                    {decisionRows.map((row) => (
                      <div key={row.label} className="repo-key-value-row">
                        <span className="card-label">{row.label}</span>
                        <span>{row.value}</span>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="card">
                  <div className="card-header">
                    <h2 className="card-title" style={{ fontSize: "18px" }}>
                      Evidence & Notes
                    </h2>
                    <button className="btn btn-sm" type="button">
                      + Add Note
                    </button>
                  </div>
                  <div className="repo-note-list">
                    {(detail.analysis_summary?.cons ?? ["No risk notes are stored yet."]).map((note) => (
                      <p key={note}>{note}</p>
                    ))}
                    {(detail.analysis_summary?.missing_feature_signals ?? []).map((signal) => (
                      <p key={signal}>{signal}</p>
                    ))}
                  </div>
                </section>
              </>
            ) : null}

            {activeTab === "readme" ? (
              <section className="card">
                <div className="card-header">
                  <div>
                    <h2 className="card-title" style={{ fontSize: "18px" }}>
                      README Intelligence
                    </h2>
                    <p style={{ marginTop: "6px", color: "var(--text-2)" }}>
                      Raw source and normalized parsing metadata stay visible so generated analysis
                      can be audited against the source document.
                    </p>
                  </div>
                </div>
                <div className="repo-two-col">
                  <div className="card" style={{ padding: "14px" }}>
                    <p className="card-label">Raw README Source</p>
                    <pre className="repo-code-block">
                      {detail.readme_snapshot?.content ?? "README artifact content is not available."}
                    </pre>
                  </div>
                  <div className="card" style={{ padding: "14px" }}>
                    <p className="card-label">Parsed Context</p>
                    <div className="repo-key-value-list" style={{ marginTop: "12px" }}>
                      <div className="repo-key-value-row">
                        <span className="card-label">Normalization</span>
                        <span>{detail.readme_snapshot?.normalization_version ?? "Unavailable"}</span>
                      </div>
                      <div className="repo-key-value-row">
                        <span className="card-label">Raw chars</span>
                        <span>{detail.readme_snapshot?.raw_character_count ?? "Unavailable"}</span>
                      </div>
                      <div className="repo-key-value-row">
                        <span className="card-label">Normalized chars</span>
                        <span>{detail.readme_snapshot?.normalized_character_count ?? "Unavailable"}</span>
                      </div>
                      <div className="repo-key-value-row">
                        <span className="card-label">Removed lines</span>
                        <span>{detail.readme_snapshot?.removed_line_count ?? "Unavailable"}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </section>
            ) : null}

            {activeTab === "analysis" ? (
              <section className="card">
                <div className="card-header">
                  <div>
                    <h2 className="card-title" style={{ fontSize: "18px" }}>
                      Analyst Output
                    </h2>
                    <p style={{ marginTop: "6px", color: "var(--text-2)" }}>
                      Structured output, provenance, and semantic taxonomy tags produced by Analyst.
                    </p>
                  </div>
                </div>
                <div className="repo-two-col">
                  <div className="card" style={{ padding: "14px" }}>
                    <p className="card-label">Generated Analysis Output</p>
                    <pre className="repo-code-block">
                      {JSON.stringify(detail.analysis_artifact?.payload ?? { analysis: null }, null, 2)}
                    </pre>
                  </div>
                  <div className="card" style={{ padding: "14px" }}>
                    <p className="card-label">Analysis Provenance</p>
                    <div className="repo-key-value-list" style={{ marginTop: "12px" }}>
                      <div className="repo-key-value-row">
                        <span className="card-label">Provider</span>
                        <span>{detail.analysis_artifact?.provider_name ?? "Unavailable"}</span>
                      </div>
                      <div className="repo-key-value-row">
                        <span className="card-label">Category</span>
                        <span>{detail.category ? titleCase(detail.category) : "Unclassified"}</span>
                      </div>
                      <div className="repo-key-value-row">
                        <span className="card-label">Agent tags</span>
                        <span>
                          {detail.agent_tags && detail.agent_tags.length > 0
                            ? detail.agent_tags.join(", ")
                            : "None"}
                        </span>
                      </div>
                      <div className="repo-key-value-row">
                        <span className="card-label">Generated at</span>
                        <span>{formatTimestamp(detail.analysis_summary?.analyzed_at)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </section>
            ) : null}

            {activeTab === "history" ? (
              <section className="card">
                <div className="card-header">
                  <div>
                    <h2 className="card-title" style={{ fontSize: "18px" }}>
                      Processing History
                    </h2>
                    <p style={{ marginTop: "6px", color: "var(--text-2)" }}>
                      Repository intake, triage, and analysis timestamps in one operator-facing ledger.
                    </p>
                  </div>
                </div>

                {failureContext ? (
                  <div className="card" style={{ padding: "14px", borderColor: "rgba(217, 79, 79, 0.28)", background: "var(--red-dim)" }}>
                    <p className="card-label" style={{ color: "var(--red)" }}>
                      Active failure context
                    </p>
                    <p style={{ marginTop: "8px", fontWeight: 600 }}>
                      {titleCase(failureContext.stage)} failure at {titleCase(failureContext.step)}
                    </p>
                    <p style={{ marginTop: "6px", color: "var(--text-1)" }}>
                      Error: {failureContext.error_message ?? "No failure message recorded."}
                    </p>
                    <p style={{ marginTop: "6px", color: "var(--text-2)" }}>
                      Recorded at: {formatTimestamp(failureContext.failed_at)}
                    </p>
                  </div>
                ) : (
                  <div className="card" style={{ padding: "14px", borderColor: "rgba(61, 186, 106, 0.24)", background: "var(--green-dim)" }}>
                    <p className="card-label" style={{ color: "var(--green)" }}>
                      Operational state
                    </p>
                    <p style={{ marginTop: "8px", fontWeight: 600 }}>
                      No repository processing failure is currently recorded.
                    </p>
                    <p style={{ marginTop: "6px", color: "var(--text-1)" }}>
                      Use this timeline to confirm which stage is pending, complete, or blocked before escalating.
                    </p>
                  </div>
                )}

                <div className="repo-key-value-list" style={{ marginTop: "16px" }}>
                  {historyRows.map(([label, value]) => (
                    <div key={label} className="repo-key-value-row">
                      <span className="card-label">{label}</span>
                      <span>{value}</span>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}
          </div>

          <aside className="repo-dossier-rail">
            <section className="card">
              <div className="card-header">
                <h2 className="card-title" style={{ fontSize: "18px" }}>
                  Tags & Categories
                </h2>
              </div>

              {curationError ? (
                <p className="card" style={{ padding: "12px", marginBottom: "12px", borderColor: "rgba(217, 79, 79, 0.28)", background: "var(--red-dim)" }}>
                  {curationError}
                </p>
              ) : null}

              <div className="repo-rail-section">
                <p className="card-label">Agent Tags</p>
                {renderTagList(detail.agent_tags ?? [], "tag tag-agent")}
              </div>

              <div className="repo-rail-section">
                <p className="card-label">Category Signals</p>
                {renderTagList(categorySignals, "tag tag-active")}
              </div>

              <div className="repo-rail-section">
                <p className="card-label">User Tags</p>
                {renderTagList(detail.user_tags, "tag tag-user", "No user tags added yet")}
                <form
                  className="repo-inline-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const normalizedTag = newUserTag.trim();
                    if (normalizedTag.length === 0 || addTagMutation.isPending) {
                      return;
                    }
                    addTagMutation.mutate(normalizedTag);
                  }}
                >
                  <input
                    aria-label="Add user tag"
                    className="input"
                    maxLength={100}
                    placeholder="Add user tag"
                    type="text"
                    value={newUserTag}
                    onChange={(event) => setNewUserTag(event.target.value)}
                  />
                  <button
                    className="btn btn-sm"
                    disabled={newUserTag.trim().length === 0 || addTagMutation.isPending}
                    type="submit"
                  >
                    Add tag
                  </button>
                </form>
                {detail.user_tags.length > 0 ? (
                  <div className="repo-tag-cluster" style={{ marginTop: "10px" }}>
                    {detail.user_tags.map((tag) => (
                      <button
                        key={tag}
                        aria-label={`Remove ${tag} tag`}
                        className="tag tag-user"
                        type="button"
                        onClick={() => removeTagMutation.mutate(tag)}
                      >
                        {tag} ×
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </section>

            {ACTIONS.map((action) => (
              <section key={action.key} className="card">
                <div className="card-header">
                  <h2 className="card-title" style={{ fontSize: "18px" }}>
                    {action.title}
                  </h2>
                </div>
                <div className="repo-key-value-list">
                  <div className="repo-key-value-row">
                    <span className="card-label">Object</span>
                    <span>{detail.repository_name}</span>
                  </div>
                  <div className="repo-key-value-row">
                    <span className="card-label">Destination</span>
                    <span>{action.destination}</span>
                  </div>
                  <div className="repo-key-value-row">
                    <span className="card-label">Result</span>
                    <span>{action.expectedResult}</span>
                  </div>
                </div>
                <button className="btn btn-primary" style={{ marginTop: "14px", width: "100%" }} type="button" onClick={() => setSelectedAction(action)}>
                  {action.buttonLabel}
                </button>
              </section>
            ))}

            <section className="card">
              <div className="card-header">
                <h2 className="card-title" style={{ fontSize: "18px" }}>
                  What Happens
                </h2>
              </div>
              {selectedAction ? (
                <div className="repo-key-value-list">
                  <div className="repo-key-value-row">
                    <span className="card-label">Selected</span>
                    <span>{selectedAction.title}</span>
                  </div>
                  <div className="repo-key-value-row">
                    <span className="card-label">Destination</span>
                    <span>{selectedAction.destination}</span>
                  </div>
                  <div className="repo-key-value-row">
                    <span className="card-label">Expected Result</span>
                    <span>{selectedAction.expectedResult}</span>
                  </div>
                </div>
              ) : (
                <p style={{ color: "var(--text-2)" }}>
                  Choose an action from the rail to preview what the next workflow will do.
                </p>
              )}
            </section>
          </aside>
        </div>
      </main>
    </>
  );
}

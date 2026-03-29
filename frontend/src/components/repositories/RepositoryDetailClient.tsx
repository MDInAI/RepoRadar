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
import { formatAppDateTime } from "@/lib/time";

type RepositoryTab = "overview" | "readme" | "analysis" | "related" | "history";
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
  { key: "related", label: "Related Repos" },
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
  return formatAppDateTime(value);
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

function renderTimestampStat(
  value: string | null | undefined,
  label: string,
) {
  return (
    <div className="repo-hero-stat" style={{ display: "flex", flexDirection: "column" }}>
      <span className="repo-hero-stat-value" style={{ fontSize: "13px", lineHeight: 1.4 }}>
        {formatTimestamp(value)}
      </span>
      <span className="repo-hero-stat-label">{label}</span>
      <span style={{ marginTop: "4px", color: "var(--text-3)", fontSize: "11px" }}>
        {formatRelativeDate(value)}
      </span>
    </div>
  );
}

function titleCase(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getDiscoverySourceLabel(source: string): string {
  if (source === "idea_scout") return "Scout";
  if (source === "backfill") return "Backfill";
  if (source === "firehose") return "Firehose";
  return titleCase(source);
}

function getDiscoverySourceBadgeClass(source: string): string {
  if (source === "idea_scout") return "tag tag-scout";
  if (source === "backfill") return "tag tag-backfill";
  return "tag tag-active"; // firehose
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

function formatScore(value: number | null | undefined, suffix = "/100"): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "Unavailable";
  }
  return `${value}${suffix}`;
}

function buildScoreRows(detail: RepositoryDetailResponse) {
  const scores = detail.analysis_summary?.score_breakdown ?? {};
  return [
    { label: "Technical maturity", value: formatScore(scores.technical_maturity_score) },
    { label: "Commercial readiness", value: formatScore(scores.commercial_readiness_score) },
    { label: "Hosted gap", value: formatScore(scores.hosted_gap_score) },
    { label: "Market timing", value: formatScore(scores.market_timing_score) },
    { label: "Trust risk", value: formatScore(scores.trust_risk_score) },
  ];
}

function buildDecisionRows(detail: RepositoryDetailResponse) {
  const fit = titleCase(detail.analysis_summary?.monetization_potential ?? "unscored");
  const category = detail.category ? titleCase(detail.category) : "Unclassified";
  const analysisMode = detail.analysis_summary?.analysis_mode
    ? titleCase(detail.analysis_summary.analysis_mode)
    : "Legacy";
  const analysisOutcome = detail.analysis_summary?.analysis_outcome
    ? titleCase(detail.analysis_summary.analysis_outcome)
    : "Unavailable";
  const recommendation =
    detail.analysis_summary?.recommended_action ??
    (detail.analysis_summary?.monetization_potential === "high"
      ? "Create family + Combiner brief"
      : detail.analysis_summary?.monetization_potential === "medium"
        ? "Keep on watchlist and gather more evidence"
        : "Monitor only");

  return [
    { label: "Monetization", value: `${fit} fit` },
    { label: "Category", value: category },
    {
      label: "Category confidence",
      value: formatScore(detail.analysis_summary?.category_confidence_score),
    },
    {
      label: "Market timing",
      value:
        detail.stargazers_count >= 1000
          ? "Strong community signal"
          : "Needs more demand validation",
    },
    {
      label: "Analyst confidence",
      value: formatScore(detail.analysis_summary?.confidence_score),
    },
    { label: "Analysis mode", value: analysisMode },
    { label: "Analysis outcome", value: analysisOutcome },
    { label: "Recommended action", value: recommendation },
  ];
}

function buildHistoryRows(detail: RepositoryDetailResponse) {
  return [
    [
      "Firehose feed",
      detail.firehose_discovery_mode ? titleCase(detail.firehose_discovery_mode) : "Not firehose",
    ],
    ["GitHub created", formatTimestamp(detail.github_created_at)],
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
  if (detail.firehose_discovery_mode) {
    signals.add(`${titleCase(detail.firehose_discovery_mode)} feed`);
  }
  if (detail.analysis_summary?.monetization_potential) {
    signals.add(`${titleCase(detail.analysis_summary.monetization_potential)} fit`);
  }
  return [...signals];
}

function buildSummaryParagraph(detail: RepositoryDetailResponse): string {
  if (detail.analysis_summary?.analysis_summary_short) {
    return detail.analysis_summary.analysis_summary_short;
  }
  if (detail.analysis_summary?.problem_statement) {
    return detail.analysis_summary.problem_statement;
  }
  if (detail.analysis_summary?.evidence_summary) {
    return detail.analysis_summary.evidence_summary;
  }
  if (detail.analysis_summary?.pros?.length) {
    return detail.analysis_summary.pros.join(" ");
  }
  if (detail.repository_description) {
    return detail.repository_description;
  }
  return "Analysis output is not available yet. Once Analyst completes, this card will summarize fit, product signals, and missing commercial gaps.";
}

function buildEvidenceNotes(detail: RepositoryDetailResponse): string[] {
  const notes = [
    ...(detail.analysis_summary?.insufficient_evidence_reason
      ? [detail.analysis_summary.insufficient_evidence_reason]
      : []),
    ...(detail.analysis_summary?.evidence_summary ? [detail.analysis_summary.evidence_summary] : []),
    ...(detail.analysis_summary?.analysis_summary_long ? [detail.analysis_summary.analysis_summary_long] : []),
    ...(detail.analysis_summary?.open_problems ? [detail.analysis_summary.open_problems] : []),
    ...(detail.analysis_summary?.contradictions ?? []),
    ...(detail.analysis_summary?.missing_information ?? []),
    ...(detail.analysis_summary?.red_flags ?? []),
    ...(detail.analysis_summary?.cons ?? []),
    ...(detail.analysis_summary?.missing_feature_signals ?? []),
  ]
    .map((value) => value.trim())
    .filter((value) => value.length > 0);

  if (notes.length > 0) {
    const seen = new Set<string>();
    return notes.filter((note) => {
      if (seen.has(note)) {
        return false;
      }
      seen.add(note);
      return true;
    });
  }

  return ["No risk notes or missing-feature evidence are stored for this repository yet."];
}

function buildActionReason(detail: RepositoryDetailResponse, action: RepositoryActionDefinition): string {
  if (action.key === "family-assignment") {
    return detail.category
      ? `${titleCase(detail.category)} classification is ready for family placement`
      : "Analyst fit is ready for operator family curation";
  }
  if (action.key === "combiner-draft") {
    return detail.analysis_summary?.monetization_potential === "high"
      ? "High-fit analysis is ready for synthesis"
      : "Use the current dossier summary as Combiner input";
  }
  return detail.agent_tags && detail.agent_tags.length > 0
    ? `Use ${detail.agent_tags.slice(0, 2).join(" + ")} tags as the similarity seed`
    : "Use repository metadata and README signals as the similarity seed";
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
  const scoreRows = useMemo(() => (detail ? buildScoreRows(detail) : []), [detail]);
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
        <section
          className="card"
          style={{ borderColor: "rgba(217, 79, 79, 0.28)", background: "var(--red-dim)" }}
        >
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
  const evidenceNotes = buildEvidenceNotes(detail);
  const readmeUnavailableMessage =
    detail.readme_snapshot?.content ??
    (detail.triage_status === "rejected"
      ? "README was not captured in Agentic Workflow because this repository was rejected during Bouncer triage before analysis ran. GitHub can still have a README even when no README artifact exists here yet."
      : detail.triage_status === "accepted" && detail.analysis_status !== "completed"
        ? "README capture is still pending. This repository has passed triage, but Analyst has not finished processing it yet."
      : "README artifact content is not available yet.");
  const summaryParagraph = buildSummaryParagraph(detail);
  const recommendedAction =
    decisionRows.find((row) => row.label === "Recommended action")?.value ?? "Review dossier";
  const familyCount = detail.idea_family_ids.length;

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Repository Detail</span>
        <span className="topbar-breadcrumb">dossier / {detail.repository_name}</span>
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
            <div className="repo-hero-stats">
              <div className="repo-hero-stat" style={{ display: "flex", flexDirection: "column" }}>
                <span className="repo-hero-stat-value">{detail.stargazers_count.toLocaleString()}</span>
                <span className="repo-hero-stat-label">Stars</span>
              </div>
              <div className="repo-hero-stat" style={{ display: "flex", flexDirection: "column" }}>
                <span className="repo-hero-stat-value">{detail.forks_count.toLocaleString()}</span>
                <span className="repo-hero-stat-label">Forks</span>
              </div>
              {renderTimestampStat(detail.github_created_at, "Created")}
              {renderTimestampStat(detail.discovered_at, "Discovered")}
              {renderTimestampStat(detail.pushed_at, "Last Commit")}
            </div>
          </div>

          <div className="repo-hero-badges">
            <a
              className="btn"
              href={`https://github.com/${detail.owner_login}/${detail.repository_name}`}
              rel="noreferrer"
              target="_blank"
            >
              ↗ Open on GitHub
            </a>
            <button
              aria-label={detail.is_starred ? "Unstar repository" : "Star repository"}
              className={`btn ${detail.is_starred ? "btn-primary" : ""}`}
              type="button"
              onClick={() => starMutation.mutate(!detail.is_starred)}
            >
              {detail.is_starred ? "★ Watchlisted" : "☆ Watchlist"}
            </button>
            <span className="badge badge-green">{titleCase(detail.analysis_status)}</span>
            <span className={getDiscoverySourceBadgeClass(detail.discovery_source)}>
              {getDiscoverySourceLabel(detail.discovery_source)}
            </span>
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
              <span className="repo-tab-label">{tab.label}</span>
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
                    {typeof detail.analysis_summary?.confidence_score === "number" ? (
                      <span className="badge badge-blue">
                        {detail.analysis_summary.confidence_score}/100 Confidence
                      </span>
                    ) : detail.analysis_summary?.monetization_potential ? (
                      <span className="badge badge-green">
                        {titleCase(detail.analysis_summary.monetization_potential)} Fit
                      </span>
                    ) : null}
                  </div>
                  <p className="repo-summary-copy">{summaryParagraph}</p>
                  <div className="repo-insight-grid">
                    <div className="repo-inline-card">
                      <p className="card-label">Discovery Route</p>
                      <p className="repo-inline-card-value">
                        {getDiscoverySourceLabel(detail.discovery_source)}
                      </p>
                    </div>
                    <div className="repo-inline-card">
                      <p className="card-label">Triage</p>
                      <p className="repo-inline-card-value">{titleCase(detail.triage_status)}</p>
                    </div>
                    <div className="repo-inline-card">
                      <p className="card-label">Analysis</p>
                      <p className="repo-inline-card-value">{titleCase(detail.analysis_status)}</p>
                    </div>
                    <div className="repo-inline-card">
                      <p className="card-label">Target Customer</p>
                      <p className="repo-inline-card-value">
                        {detail.analysis_summary?.target_customer ?? "Unavailable"}
                      </p>
                    </div>
                  </div>
                  {detail.scout_context && (
                    <div className="repo-scout-origin">
                      <p className="card-label" style={{ marginBottom: "6px" }}>Scout Discovery Origin</p>
                      <div className="repo-scout-origin-body">
                        <div className="repo-scout-origin-row">
                          <span className="repo-scout-origin-key">Search</span>
                          <span className="repo-scout-origin-val">
                            {detail.scout_context.idea_text.length > 80
                              ? detail.scout_context.idea_text.slice(0, 80) + "…"
                              : detail.scout_context.idea_text}
                          </span>
                        </div>
                        <div className="repo-scout-origin-row">
                          <span className="repo-scout-origin-key">Query {detail.scout_context.query_index + 1}</span>
                          <span className="repo-scout-origin-val repo-scout-origin-query">
                            {detail.scout_context.query_text || "—"}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}
                </section>

                <div className="repo-paired-grid">
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
                        Triage Context
                      </h2>
                    </div>
                    <div className="repo-note-list">
                      <p>
                        Status: <strong>{titleCase(detail.triage_status)}</strong>
                      </p>
                      <p>
                        {detail.triage.explanation?.summary ??
                          "No triage explanation has been stored yet."}
                      </p>
                      <p>
                        Include rules:{" "}
                        {detail.triage.explanation?.matched_include_rules?.length
                          ? detail.triage.explanation.matched_include_rules.join(", ")
                          : "None"}
                      </p>
                      <p>
                        Exclude rules:{" "}
                        {detail.triage.explanation?.matched_exclude_rules?.length
                          ? detail.triage.explanation.matched_exclude_rules.join(", ")
                          : "None"}
                      </p>
                    </div>
                  </section>
                </div>

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
                    {evidenceNotes.map((note, index) => (
                      <p key={`${index}-${note}`}>{note}</p>
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
                      {readmeUnavailableMessage}
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
                        <span className="card-label">Model</span>
                        <span>{detail.analysis_artifact?.model_name ?? "Unavailable"}</span>
                      </div>
                      <div className="repo-key-value-row">
                        <span className="card-label">Category</span>
                        <span>{detail.category ? titleCase(detail.category) : "Unclassified"}</span>
                      </div>
                      <div className="repo-key-value-row">
                        <span className="card-label">Category confidence</span>
                        <span>{formatScore(detail.analysis_summary?.category_confidence_score)}</span>
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
                        <span className="card-label">Target audience</span>
                        <span>{detail.analysis_summary?.target_audience ?? "Unavailable"}</span>
                      </div>
                      <div className="repo-key-value-row">
                        <span className="card-label">Technical stack</span>
                        <span>{detail.analysis_summary?.technical_stack ?? "Unavailable"}</span>
                      </div>
                      <div className="repo-key-value-row">
                        <span className="card-label">Business model</span>
                        <span>{detail.analysis_summary?.business_model_guess ?? "Unavailable"}</span>
                      </div>
                      <div className="repo-key-value-row">
                        <span className="card-label">Competitors</span>
                        <span>{detail.analysis_summary?.competitors ?? "Unavailable"}</span>
                      </div>
                      <div className="repo-key-value-row">
                        <span className="card-label">Recommended action</span>
                        <span>{detail.analysis_summary?.recommended_action ?? "Unavailable"}</span>
                      </div>
                      {scoreRows.map((row) => (
                        <div key={row.label} className="repo-key-value-row">
                          <span className="card-label">{row.label}</span>
                          <span>{row.value}</span>
                        </div>
                      ))}
                      <div className="repo-key-value-row">
                        <span className="card-label">Generated at</span>
                        <span>{formatTimestamp(detail.analysis_summary?.analyzed_at)}</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="repo-two-col" style={{ marginTop: "16px" }}>
                  <div className="card" style={{ padding: "14px" }}>
                    <p className="card-label">Contradictions & Missing Evidence</p>
                    <div className="repo-list-block" style={{ marginTop: "12px" }}>
                      {[
                        ...(detail.analysis_summary?.contradictions ?? []),
                        ...(detail.analysis_summary?.missing_information ?? []),
                      ].length > 0 ? (
                        <ul style={{ margin: 0, paddingLeft: "18px", color: "var(--text-2)" }}>
                          {[
                            ...(detail.analysis_summary?.contradictions ?? []),
                            ...(detail.analysis_summary?.missing_information ?? []),
                          ].map((item) => (
                            <li key={item} style={{ marginTop: "8px" }}>
                              {item}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p style={{ color: "var(--text-2)", margin: 0 }}>
                          No contradiction or missing-information signals are stored for this run.
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="card" style={{ padding: "14px" }}>
                    <p className="card-label">Deep Summary</p>
                    <p style={{ marginTop: "10px", color: "var(--text-2)" }}>
                      {detail.analysis_summary?.analysis_summary_long ??
                        detail.analysis_summary?.evidence_summary ??
                        "Long-form analyst summary is not available yet."}
                    </p>
                  </div>
                </div>
              </section>
            ) : null}

            {activeTab === "related" ? (
              <div className="repo-paired-grid">
                <section className="card">
                  <div className="card-header">
                    <div>
                      <h2 className="card-title" style={{ fontSize: "18px" }}>
                        Similar Project Scan
                      </h2>
                      <p style={{ marginTop: "6px", color: "var(--text-2)" }}>
                        Seed similarity using the current category, tags, and README themes.
                      </p>
                    </div>
                  </div>
                  <div className="repo-key-value-list">
                    <div className="repo-key-value-row">
                      <span className="card-label">Seed</span>
                      <span>{detail.repository_name}</span>
                    </div>
                    <div className="repo-key-value-row">
                      <span className="card-label">Basis</span>
                      <span>
                        {detail.category ? titleCase(detail.category) : "Repository metadata"} + tags
                      </span>
                    </div>
                    <div className="repo-key-value-row">
                      <span className="card-label">Depth</span>
                      <span>Top 20 similar repos</span>
                    </div>
                    <div className="repo-key-value-row">
                      <span className="card-label">Destination</span>
                      <span>Repositories (filtered)</span>
                    </div>
                  </div>
                  <button
                    className="btn"
                    style={{ marginTop: "14px" }}
                    type="button"
                    onClick={() => setSelectedAction(ACTIONS[2])}
                  >
                    Scan repos similar to {detail.repository_name}
                  </button>
                </section>

                <section className="card">
                  <div className="card-header">
                    <div>
                      <h2 className="card-title" style={{ fontSize: "18px" }}>
                        Family Links
                      </h2>
                      <p style={{ marginTop: "6px", color: "var(--text-2)" }}>
                        Track whether this dossier is already tied to an ideas family.
                      </p>
                    </div>
                  </div>
                  <div className="repo-key-value-list">
                    <div className="repo-key-value-row">
                      <span className="card-label">Linked families</span>
                      <span>{familyCount > 0 ? familyCount.toString() : "None yet"}</span>
                    </div>
                    <div className="repo-key-value-row">
                      <span className="card-label">Recommended action</span>
                      <span>{recommendedAction}</span>
                    </div>
                    <div className="repo-key-value-row">
                      <span className="card-label">User curation</span>
                      <span>{detail.user_tags.length > 0 ? detail.user_tags.join(", ") : "No user tags"}</span>
                    </div>
                  </div>
                </section>
              </div>
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
                  <div
                    className="card"
                    style={{ padding: "14px", borderColor: "rgba(217, 79, 79, 0.28)", background: "var(--red-dim)" }}
                  >
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
                  <div
                    className="card"
                    style={{ padding: "14px", borderColor: "rgba(61, 186, 106, 0.24)", background: "var(--green-dim)" }}
                  >
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
                <p
                  className="card"
                  style={{ padding: "12px", marginBottom: "12px", borderColor: "rgba(217, 79, 79, 0.28)", background: "var(--red-dim)" }}
                >
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
                <p className="card-label">Suggested Categories</p>
                {renderTagList(
                  detail.analysis_summary?.suggested_new_categories ?? [],
                  "tag tag-active",
                  "No suggested categories",
                )}
              </div>

              <div className="repo-rail-section">
                <p className="card-label">Suggested Tags</p>
                {renderTagList(
                  detail.analysis_summary?.suggested_new_tags ?? [],
                  "tag tag-agent",
                  "No suggested tags",
                )}
              </div>

              <div className="repo-rail-section">
                <p className="card-label">Score Breakdown</p>
                <div className="repo-key-value-list" style={{ marginTop: "10px" }}>
                  {scoreRows.map((row) => (
                    <div key={row.label} className="repo-key-value-row">
                      <span>{row.label}</span>
                      <span>{row.value}</span>
                    </div>
                  ))}
                </div>
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

            <section className="card">
              <div className="card-header">
                <h2 className="card-title" style={{ fontSize: "18px" }}>
                  Action Launcher
                </h2>
              </div>
              <div className="repo-rail-actions">
                {ACTIONS.map((action) => (
                  <button
                    aria-label={action.buttonLabel}
                    key={action.key}
                    className={`repo-action-card ${selectedAction?.key === action.key ? "active" : ""}`}
                    type="button"
                    onClick={() => setSelectedAction(action)}
                  >
                    <span className="repo-action-title">{action.title}</span>
                    <span className="repo-action-meta">{buildActionReason(detail, action)}</span>
                  </button>
                ))}
              </div>
            </section>

            <section className="card">
              <div className="card-header">
                <h2 className="card-title" style={{ fontSize: "18px" }}>
                  What Happens
                </h2>
              </div>
              {selectedAction ? (
                <>
                  <div className="repo-key-value-list">
                    <div className="repo-key-value-row">
                      <span className="card-label">Selected</span>
                      <span>{selectedAction.title}</span>
                    </div>
                    <div className="repo-key-value-row">
                      <span className="card-label">Reason</span>
                      <span>{buildActionReason(detail, selectedAction)}</span>
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
                  <button className="btn btn-primary" style={{ marginTop: "14px", width: "100%" }} type="button">
                    {selectedAction.buttonLabel}
                  </button>
                </>
              ) : (
                <p style={{ color: "var(--text-2)" }}>
                  Choose an action from the rail to preview what the next workflow will do.
                </p>
              )}
            </section>

            <section className="card">
              <div className="card-header">
                <h2 className="card-title" style={{ fontSize: "18px" }}>
                  Processing Monitor
                </h2>
              </div>
              <div className="repo-key-value-list">
                <div className="repo-key-value-row">
                  <span className="card-label">Intake</span>
                  <span>{titleCase(detail.intake_status)}</span>
                </div>
                <div className="repo-key-value-row">
                  <span className="card-label">Triage</span>
                  <span>{titleCase(detail.triage_status)}</span>
                </div>
                <div className="repo-key-value-row">
                  <span className="card-label">Analysis</span>
                  <span>{titleCase(detail.analysis_status)}</span>
                </div>
                <div className="repo-key-value-row">
                  <span className="card-label">Last Updated</span>
                  <span>{formatTimestamp(detail.status_updated_at)}</span>
                </div>
              </div>
            </section>
          </aside>
        </div>
      </main>
    </>
  );
}

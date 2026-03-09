"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  addRepositoryUserTag,
  fetchRepositoryDetail,
  getRepositoryDetailQueryKey,
  removeRepositoryUserTag,
  updateRepositoryStar,
  type RepositoryAnalysisArtifact,
  type RepositoryDetailResponse,
} from "@/api/repositories";

import {
  formatAnalysisStatusLabel,
  formatCompactNumber,
  formatDiscoverySourceLabel,
  formatMonetizationLabel,
  formatRelativeDate,
  getFitBadgeClassName,
  getStatusBadgeClassName,
} from "./catalogPresentation";

type RepositoryActionKey = "family-assignment" | "combiner-draft" | "similar-project-scan";

interface RepositoryActionDefinition {
  key: RepositoryActionKey;
  title: string;
  destination: string;
  expectedResult: string;
  buttonLabel: string;
}

const ACTIONS: RepositoryActionDefinition[] = [
  {
    key: "family-assignment",
    title: "Family Assignment",
    destination: "Ideas > Family Workspace",
    expectedResult:
      "The repository is staged for inclusion in a future idea family grouping workflow.",
    buttonLabel: "Stage family assignment",
  },
  {
    key: "combiner-draft",
    title: "Create Combiner Brief",
    destination: "Ideas > Combiner Results",
    expectedResult:
      "A synthesis draft is prepared so the Combiner can generate a composite business idea.",
    buttonLabel: "Create Combiner brief",
  },
  {
    key: "similar-project-scan",
    title: "Similar-Project Scan",
    destination: "Repositories > Similar Results",
    expectedResult:
      "A follow-up scan is queued to surface repositories with adjacent market or product signals.",
    buttonLabel: "Queue similar-project scan",
  },
];

function formatStatusLabel(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatTriageExplanationKind(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function collectAgentTags(detail: RepositoryDetailResponse): string[] {
  const explanation = detail.triage.explanation;
  if (!explanation) {
    return [];
  }
  return [...explanation.matched_include_rules, ...explanation.matched_exclude_rules];
}

function collectCategorySignals(detail: RepositoryDetailResponse): string[] {
  const categories = new Set<string>();
  categories.add(formatDiscoverySourceLabel(detail.discovery_source));
  if (detail.analysis_summary?.monetization_potential) {
    categories.add(formatMonetizationLabel(detail.analysis_summary.monetization_potential));
  }
  if (detail.analysis_summary?.missing_feature_signals.length) {
    categories.add("Missing feature signals");
  }
  return [...categories];
}

function renderAnalysisPayload(analysisArtifact: RepositoryAnalysisArtifact | null) {
  const payload = analysisArtifact?.payload;
  if (!payload) {
    return (
      <p className="text-sm leading-6 text-slate-600">
        No generated analysis artifact is available yet.
      </p>
    );
  }

  return (
    <pre className="overflow-x-auto rounded-[1.4rem] bg-slate-950 px-4 py-4 text-xs leading-6 text-slate-100">
      {JSON.stringify(payload, null, 2)}
    </pre>
  );
}

export function RepositoryDetailClient({ repositoryId }: { repositoryId: number }) {
  const queryClient = useQueryClient();
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
      setCurationError(error instanceof Error ? error.message : "Unable to update starred state.");
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
    onMutate: () => {
      setCurationError(null);
    },
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
    onMutate: () => {
      setCurationError(null);
    },
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

  if (!Number.isFinite(repositoryId) || repositoryId <= 0) {
    return (
      <main className="min-h-screen bg-[linear-gradient(180deg,#fff8f1_0%,#f8fafc_40%,#dbeafe_100%)] px-6 py-10 text-slate-900">
        <div className="mx-auto max-w-7xl rounded-[2rem] border border-amber-200 bg-amber-50 px-6 py-12 shadow-[0_20px_60px_-36px_rgba(180,83,9,0.35)]">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-amber-700">
            Invalid Route
          </p>
          <h1 className="mt-3 text-2xl font-semibold text-amber-950">
            Repository ID is missing or invalid
          </h1>
          <p className="mt-3 max-w-2xl text-sm text-amber-900">
            Open the dossier from the repository catalog so the route can resolve a valid
            repository identifier.
          </p>
        </div>
      </main>
    );
  }

  if (detailQuery.isLoading && !detailQuery.data) {
    return (
      <main className="min-h-screen bg-[linear-gradient(180deg,#fff8f1_0%,#f8fafc_40%,#dbeafe_100%)] px-6 py-10 text-slate-900">
        <div className="mx-auto flex max-w-7xl flex-col gap-6">
          <section className="rounded-[2rem] border border-black/10 bg-white/90 px-6 py-16 shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)]">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
              Loading
            </p>
            <h1 className="mt-3 text-3xl font-semibold text-slate-950">
              Hydrating repository dossier
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
              Pulling repository metadata, README context, triage rationale, and generated
              analysis artifacts into the multi-pane detail surface.
            </p>
          </section>
        </div>
      </main>
    );
  }

  if (detailQuery.isError || !detailQuery.data) {
    const errorMessage =
      detailQuery.error instanceof Error
        ? detailQuery.error.message
        : "Unable to load the repository dossier.";
    return (
      <main className="min-h-screen bg-[linear-gradient(180deg,#fff8f1_0%,#f8fafc_40%,#dbeafe_100%)] px-6 py-10 text-slate-900">
        <div className="mx-auto max-w-7xl rounded-[2rem] border border-rose-200 bg-rose-50 px-6 py-12 shadow-[0_20px_60px_-36px_rgba(244,63,94,0.35)]">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-rose-700">
            Dossier Error
          </p>
          <h1 className="mt-3 text-2xl font-semibold text-rose-950">
            Unable to load repository detail
          </h1>
          <p className="mt-3 max-w-2xl text-sm text-rose-900">{errorMessage}</p>
          <button
            className="mt-5 rounded-full border border-rose-300 bg-white px-4 py-2 text-sm font-semibold text-rose-900 transition hover:bg-rose-100"
            type="button"
            onClick={() => {
              void detailQuery.refetch();
            }}
          >
            Retry fetch
          </button>
        </div>
      </main>
    );
  }

  const detail = detailQuery.data;
  const triageExplanation = detail.triage.explanation;
  const agentTags = collectAgentTags(detail);
  const categorySignals = collectCategorySignals(detail);

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#fff8f1_0%,#f8fafc_40%,#dbeafe_100%)] px-6 py-10 text-slate-900">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <header className="rounded-[2.2rem] border border-black/10 bg-white/85 px-6 py-7 shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)] backdrop-blur">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
            <div className="max-w-4xl">
              <p className="text-xs font-semibold uppercase tracking-[0.32em] text-orange-700">
                Repository Dossier
              </p>
              <h1 className="mt-3 text-4xl font-semibold tracking-tight text-slate-950">
                {detail.full_name}
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-600">
                {detail.repository_description ?? "No repository description is available yet."}
              </p>

              <div className="mt-5 flex flex-wrap gap-3">
                <span className="rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-800">
                  Queue: {formatStatusLabel(detail.queue_status)}
                </span>
                <span
                  className={`rounded-full border px-3 py-1 text-xs font-semibold ${getStatusBadgeClassName(
                    detail.analysis_status,
                  )}`}
                >
                  Analysis: {formatAnalysisStatusLabel(detail.analysis_status)}
                </span>
                <span
                  className={`rounded-full border px-3 py-1 text-xs font-semibold ${getFitBadgeClassName(
                    detail.analysis_summary?.monetization_potential ?? null,
                  )}`}
                >
                  Fit: {formatMonetizationLabel(detail.analysis_summary?.monetization_potential ?? null)}
                </span>
                <button
                  aria-label={detail.is_starred ? "Unstar repository" : "Star repository"}
                  aria-pressed={detail.is_starred}
                  className={`inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-xs font-semibold transition ${
                    detail.is_starred
                      ? "border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100"
                      : "border-slate-200 bg-white text-slate-700 hover:border-amber-300 hover:text-amber-700"
                  }`}
                  disabled={starMutation.isPending}
                  type="button"
                  onClick={() => {
                    starMutation.mutate(!detail.is_starred);
                  }}
                >
                  <span aria-hidden="true">{detail.is_starred ? "★" : "☆"}</span>
                  {detail.is_starred ? "Starred" : "Add to starred"}
                </button>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:w-[24rem]">
              <div className="rounded-[1.6rem] border border-orange-200 bg-orange-50/90 px-4 py-4">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-orange-700">
                  Trust Signals
                </p>
                <div className="mt-3 space-y-2 text-sm text-orange-950">
                  <p>
                    <span className="font-semibold">{formatCompactNumber(detail.stargazers_count)}</span>{" "}
                    stars
                  </p>
                  <p>
                    <span className="font-semibold">{formatCompactNumber(detail.forks_count)}</span>{" "}
                    forks
                  </p>
                  <p>Discovery: {formatDiscoverySourceLabel(detail.discovery_source)}</p>
                  <p>Pushed {formatRelativeDate(detail.pushed_at)}</p>
                </div>
              </div>

              <div className="rounded-[1.6rem] border border-slate-200 bg-slate-50/90 px-4 py-4">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                  Action Context
                </p>
                <div className="mt-3 space-y-2 text-sm text-slate-700">
                  <p>Object: {detail.full_name}</p>
                  <p>Route target: `/repositories/{detail.github_repository_id}`</p>
                  <p>Last status change: {formatRelativeDate(detail.status_updated_at)}</p>
                </div>
              </div>
            </div>
          </div>
        </header>

        {selectedAction ? (
          <section
            aria-live="polite"
            className="rounded-[1.8rem] border border-emerald-200 bg-emerald-50 px-6 py-5 shadow-[0_20px_60px_-40px_rgba(16,185,129,0.35)]"
            role="status"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-emerald-700">
              Action Scaffold Ready
            </p>
            <h2 className="mt-2 text-xl font-semibold text-emerald-950">{selectedAction.title}</h2>
            <p className="mt-3 text-sm text-emerald-950">
              <span className="font-semibold">Object:</span> {detail.full_name}
            </p>
            <p className="mt-1 text-sm text-emerald-950">
              <span className="font-semibold">Destination:</span> {selectedAction.destination}
            </p>
            <p className="mt-1 text-sm text-emerald-950">
              <span className="font-semibold">Expected Result:</span> {selectedAction.expectedResult}
            </p>
          </section>
        ) : null}

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="flex flex-col gap-6">
            <section className="rounded-[2rem] border border-black/10 bg-white/90 px-6 py-6 shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)]">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                    Repo Overview
                  </p>
                  <h2 className="mt-2 text-2xl font-semibold text-slate-950">
                    Repository metadata and triage context
                  </h2>
                </div>

                <div className="grid gap-2 text-sm text-slate-700 sm:grid-cols-2">
                  <p>Owner: {detail.owner_login}</p>
                  <p>Repository: {detail.repository_name}</p>
                  <p>Provider: {detail.source_provider}</p>
                  <p>Discovered {formatRelativeDate(detail.discovered_at)}</p>
                </div>
              </div>

              <div className="mt-6 grid gap-4 lg:grid-cols-2">
                <div className="rounded-[1.6rem] border border-slate-200 bg-slate-50/80 px-5 py-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                    Triage Context
                  </p>
                  <p className="mt-3 text-sm font-semibold text-slate-950">
                    Status: {formatStatusLabel(detail.triage.triage_status)}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-slate-700">
                    {triageExplanation?.summary ??
                      "Triage explanation is not available yet for this repository."}
                  </p>
                  {triageExplanation ? (
                    <div className="mt-4 space-y-2 text-sm text-slate-700">
                      <p>
                        Explanation kind: {formatTriageExplanationKind(triageExplanation.kind)}
                      </p>
                      <p>
                        Include rules:{" "}
                        {triageExplanation.matched_include_rules.length > 0
                          ? triageExplanation.matched_include_rules.join(", ")
                          : "None"}
                      </p>
                      <p>
                        Exclude rules:{" "}
                        {triageExplanation.matched_exclude_rules.length > 0
                          ? triageExplanation.matched_exclude_rules.join(", ")
                          : "None"}
                      </p>
                    </div>
                  ) : null}
                </div>

                <div className="rounded-[1.6rem] border border-orange-200 bg-orange-50/70 px-5 py-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-orange-700">
                    Generated Summary
                  </p>
                  {detail.analysis_summary ? (
                    <div className="mt-3 space-y-3 text-sm text-orange-950">
                      <p>
                        Monetization fit:{" "}
                        <span className="font-semibold">
                          {formatMonetizationLabel(detail.analysis_summary.monetization_potential)}
                        </span>
                      </p>
                      <p>
                        Pros:{" "}
                        {detail.analysis_summary.pros.length > 0
                          ? detail.analysis_summary.pros.join(", ")
                          : "None"}
                      </p>
                      <p>
                        Risks:{" "}
                        {detail.analysis_summary.cons.length > 0
                          ? detail.analysis_summary.cons.join(", ")
                          : "None"}
                      </p>
                      <p>
                        Missing features:{" "}
                        {detail.analysis_summary.missing_feature_signals.length > 0
                          ? detail.analysis_summary.missing_feature_signals.join(", ")
                          : "None"}
                      </p>
                    </div>
                  ) : (
                    <p className="mt-3 text-sm leading-6 text-orange-950">
                      Analysis has not been generated yet.
                    </p>
                  )}
                </div>
              </div>
            </section>

            <section className="rounded-[2rem] border border-black/10 bg-white/90 px-6 py-6 shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)]">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                README Intelligence
              </p>
              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                <div className="rounded-[1.6rem] border border-sky-200 bg-sky-50/70 px-5 py-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-700">
                    Raw README Source
                  </p>
                  <p className="mt-3 text-sm leading-6 text-sky-950">
                    This pane shows the persisted README artifact, so operators can inspect source
                    material separately from generated analysis.
                  </p>
                  <pre className="mt-4 max-h-[22rem] overflow-auto rounded-[1.2rem] bg-slate-950 px-4 py-4 text-xs leading-6 text-slate-100">
                    {detail.readme_snapshot?.content ?? "README artifact content is not available."}
                  </pre>
                </div>

                <div className="rounded-[1.6rem] border border-emerald-200 bg-emerald-50/70 px-5 py-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-emerald-700">
                    Parsed Context
                  </p>
                  <div className="mt-3 space-y-2 text-sm leading-6 text-emerald-950">
                    <p>
                      Normalization version:{" "}
                      {detail.readme_snapshot?.normalization_version ?? "Unavailable"}
                    </p>
                    <p>
                      Raw characters:{" "}
                      {detail.readme_snapshot?.raw_character_count ?? "Unavailable"}
                    </p>
                    <p>
                      Normalized characters:{" "}
                      {detail.readme_snapshot?.normalized_character_count ?? "Unavailable"}
                    </p>
                    <p>
                      Removed lines: {detail.readme_snapshot?.removed_line_count ?? "Unavailable"}
                    </p>
                    <p>
                      Artifact path:{" "}
                      {detail.readme_snapshot?.artifact?.runtime_relative_path ?? "Unavailable"}
                    </p>
                  </div>
                </div>
              </div>
            </section>

            <section className="rounded-[2rem] border border-black/10 bg-white/90 px-6 py-6 shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)]">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                Analyst Output
              </p>
              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                <div className="rounded-[1.6rem] border border-orange-200 bg-orange-50/80 px-5 py-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-orange-700">
                    Generated Analysis Output
                  </p>
                  <p className="mt-3 text-sm leading-6 text-orange-950">
                    This pane shows generated analysis so it is visually distinct from the raw
                    README source shown above.
                  </p>
                  <div className="mt-4">{renderAnalysisPayload(detail.analysis_artifact)}</div>
                </div>

                <div className="rounded-[1.6rem] border border-violet-200 bg-violet-50/80 px-5 py-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-violet-700">
                    Analysis Provenance
                  </p>
                  <div className="mt-3 space-y-2 text-sm leading-6 text-violet-950">
                    <p>
                      Provider: {detail.analysis_artifact?.provider_name ?? "Unavailable"}
                    </p>
                    <p>
                      Analysis artifact:{" "}
                      {detail.analysis_artifact?.artifact?.runtime_relative_path ?? "Unavailable"}
                    </p>
                    <p>
                      README source path:{" "}
                      {typeof detail.analysis_artifact?.source_metadata.readme_artifact_path ===
                      "string"
                        ? detail.analysis_artifact.source_metadata.readme_artifact_path
                        : "Unavailable"}
                    </p>
                    <p>
                      Generated at:{" "}
                      {detail.analysis_artifact?.artifact?.generated_at
                        ? formatRelativeDate(detail.analysis_artifact.artifact.generated_at)
                        : "Unavailable"}
                    </p>
                  </div>
                </div>
              </div>
            </section>

            <section className="rounded-[2rem] border border-black/10 bg-white/90 px-6 py-6 shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)]">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                Action Launcher
              </p>
              <div className="mt-5 grid gap-4 lg:grid-cols-3">
                {ACTIONS.map((action) => (
                  <article
                    key={action.key}
                    className="rounded-[1.6rem] border border-slate-200 bg-slate-50/90 px-5 py-5"
                  >
                    <p className="text-lg font-semibold text-slate-950">{action.title}</p>
                    <div className="mt-4 space-y-2 text-sm leading-6 text-slate-700">
                      <p>
                        <span className="font-semibold text-slate-950">Object:</span>{" "}
                        {detail.full_name}
                      </p>
                      <p>
                        <span className="font-semibold text-slate-950">Destination:</span>{" "}
                        {action.destination}
                      </p>
                      <p>
                        <span className="font-semibold text-slate-950">Expected Result:</span>{" "}
                        {action.expectedResult}
                      </p>
                    </div>
                    <button
                      className="mt-5 rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
                      type="button"
                      onClick={() => {
                        setSelectedAction(action);
                      }}
                    >
                      {action.buttonLabel}
                    </button>
                  </article>
                ))}
              </div>
            </section>
          </div>

          <aside className="flex flex-col gap-6">
            <section className="rounded-[2rem] border border-black/10 bg-white/90 px-5 py-5 shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)]">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                Secondary Rail
              </p>
              <h2 className="mt-2 text-xl font-semibold text-slate-950">
                Tags, categories, watch state, and linked ideas
              </h2>

              <div className="mt-5 space-y-5">
                {curationError ? (
                  <p className="rounded-[1.2rem] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">
                    {curationError}
                  </p>
                ) : null}

                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                    Agent Tags
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {agentTags.length > 0 ? (
                      agentTags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full border border-emerald-300 bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-950"
                        >
                          {tag}
                        </span>
                      ))
                    ) : (
                      <p className="text-sm text-slate-600">No triage rule tags are stored yet.</p>
                    )}
                  </div>
                </div>

                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                    Category Signals
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {categorySignals.map((signal) => (
                      <span
                        key={signal}
                        className="rounded-full border border-orange-300 bg-orange-100 px-3 py-1 text-xs font-semibold text-orange-950"
                      >
                        {signal}
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                    User Tags
                  </p>
                  <p className="mt-3 text-sm leading-6 text-slate-700">
                    User-applied tags stay separate from agent-generated tags above so later idea
                    family workflows can distinguish operator curation from analysis output.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {detail.user_tags.length > 0 ? (
                      detail.user_tags.map((tag) => (
                        <button
                          key={tag}
                          aria-label={`Remove ${tag} tag`}
                          className="inline-flex items-center gap-2 rounded-full border border-sky-300 bg-sky-100 px-3 py-1 text-xs font-semibold text-sky-950 transition hover:bg-sky-200"
                          disabled={removeTagMutation.isPending}
                          type="button"
                          onClick={() => {
                            removeTagMutation.mutate(tag);
                          }}
                        >
                          <span>{tag}</span>
                          <span aria-hidden="true">x</span>
                        </button>
                      ))
                    ) : (
                      <p className="text-sm text-slate-600">No user tags added yet.</p>
                    )}
                  </div>
                  <form
                    className="mt-4 flex gap-2"
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
                      className="min-w-0 flex-1 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-900 outline-none transition focus:border-sky-400"
                      maxLength={100}
                      placeholder="Add user tag"
                      type="text"
                      value={newUserTag}
                      onChange={(event) => {
                        setNewUserTag(event.target.value);
                      }}
                    />
                    <button
                      className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-900 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
                      disabled={newUserTag.trim().length === 0 || addTagMutation.isPending}
                      type="submit"
                    >
                      Add tag
                    </button>
                  </form>
                </div>

                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                    Watch State
                  </p>
                  <p className="mt-3 text-sm leading-6 text-slate-700">
                    {detail.is_starred
                      ? "This repository is starred for later idea-family work."
                      : "This repository is not starred yet. Use the star control to keep it in your later-work queue."}
                  </p>
                </div>

                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                    Linked Ideas
                  </p>
                  <p className="mt-3 text-sm leading-6 text-slate-700">
                    No idea family links exist yet. Use the action launcher to stage family or
                    Combiner follow-ups from this repository.
                  </p>
                </div>
              </div>
            </section>

            <section className="rounded-[2rem] border border-black/10 bg-white/90 px-5 py-5 shadow-[0_20px_60px_-36px_rgba(15,23,42,0.45)]">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                Artifact Ledger
              </p>
              <div className="mt-4 space-y-3">
                {detail.artifacts.length > 0 ? (
                  detail.artifacts.map((artifact) => (
                    <article
                      key={`${artifact.artifact_kind}:${artifact.runtime_relative_path}`}
                      className="rounded-[1.4rem] border border-slate-200 bg-slate-50/80 px-4 py-4"
                    >
                      <p className="text-sm font-semibold text-slate-950">
                        {artifact.artifact_kind.replace("_", " ")}
                      </p>
                      <p className="mt-2 break-all text-xs leading-5 text-slate-600">
                        {artifact.runtime_relative_path}
                      </p>
                    </article>
                  ))
                ) : (
                  <p className="text-sm text-slate-600">No durable artifacts are tracked yet.</p>
                )}
              </div>
            </section>
          </aside>
        </div>
      </div>
    </main>
  );
}

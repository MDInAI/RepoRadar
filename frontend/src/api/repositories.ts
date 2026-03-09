import { getRequiredApiBaseUrl } from "./base-url";

export type RepositoryDiscoverySource = "unknown" | "firehose" | "backfill";
export type RepositoryTriageStatus = "pending" | "accepted" | "rejected";
export type RepositoryAnalysisStatus = "pending" | "in_progress" | "completed" | "failed";
export type RepositoryMonetizationPotential = "low" | "medium" | "high";
export type RepositoryCatalogSortBy = "stars" | "forks" | "pushed_at" | "ingested_at";
export type RepositoryCatalogSortOrder = "asc" | "desc";

export interface RepositoryCatalogItem {
  github_repository_id: number;
  full_name: string;
  owner_login: string;
  repository_name: string;
  repository_description: string | null;
  stargazers_count: number;
  forks_count: number;
  pushed_at: string | null;
  discovery_source: RepositoryDiscoverySource;
  triage_status: RepositoryTriageStatus;
  analysis_status: RepositoryAnalysisStatus;
  monetization_potential: RepositoryMonetizationPotential | null;
  has_readme_artifact: boolean;
  has_analysis_artifact: boolean;
}

export interface RepositoryCatalogPageResponse {
  items: RepositoryCatalogItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

interface RepositoryCatalogErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
  };
}

export interface RepositoryCatalogViewState {
  page: number;
  pageSize: number;
  sort: RepositoryCatalogSortBy;
  order: RepositoryCatalogSortOrder;
  search: string | null;
  source: RepositoryDiscoverySource | null;
  triageStatus: RepositoryTriageStatus | null;
  analysisStatus: RepositoryAnalysisStatus | null;
  monetization: RepositoryMonetizationPotential | null;
  minStars: number | null;
  maxStars: number | null;
}

export type RepositoryCatalogFilterKey =
  | "search"
  | "source"
  | "triageStatus"
  | "analysisStatus"
  | "monetization"
  | "minStars"
  | "maxStars";

export interface RepositoryCatalogFilterChip {
  key: RepositoryCatalogFilterKey;
  label: string;
}

interface SearchParamReader {
  get(name: string): string | null;
}

const DEFAULT_VIEW_STATE: RepositoryCatalogViewState = {
  page: 1,
  pageSize: 30,
  sort: "stars",
  order: "desc",
  search: null,
  source: null,
  triageStatus: null,
  analysisStatus: null,
  monetization: null,
  minStars: null,
  maxStars: null,
};

const SOURCE_VALUES: RepositoryDiscoverySource[] = ["unknown", "firehose", "backfill"];
const TRIAGE_VALUES: RepositoryTriageStatus[] = ["pending", "accepted", "rejected"];
const ANALYSIS_VALUES: RepositoryAnalysisStatus[] = [
  "pending",
  "in_progress",
  "completed",
  "failed",
];
const MONETIZATION_VALUES: RepositoryMonetizationPotential[] = ["low", "medium", "high"];
const SORT_VALUES: RepositoryCatalogSortBy[] = ["stars", "forks", "pushed_at", "ingested_at"];
const ORDER_VALUES: RepositoryCatalogSortOrder[] = ["asc", "desc"];

export class RepositoryCatalogRequestError extends Error {
  status: number;
  code: string | undefined;
  details: Record<string, unknown>;

  constructor(
    message: string,
    options: {
      status: number;
      code?: string;
      details?: Record<string, unknown>;
    },
  ) {
    super(message);
    this.name = "RepositoryCatalogRequestError";
    this.status = options.status;
    this.code = options.code;
    this.details = options.details ?? {};
  }
}

function parsePositiveInt(value: string | null, fallback: number): number {
  if (!value) {
    return fallback;
  }

  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseNonNegativeInt(value: string | null): number | null {
  if (!value) {
    return null;
  }

  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function parseEnumValue<TValue extends string>(
  value: string | null,
  allowedValues: readonly TValue[],
): TValue | null {
  if (!value) {
    return null;
  }

  return allowedValues.includes(value as TValue) ? (value as TValue) : null;
}

export function parseRepositoryCatalogSearchParams(
  searchParams: SearchParamReader,
): RepositoryCatalogViewState {
  const search = searchParams.get("search")?.trim() ?? "";
  return {
    page: parsePositiveInt(searchParams.get("page"), DEFAULT_VIEW_STATE.page),
    pageSize: Math.min(
      100,
      parsePositiveInt(searchParams.get("pageSize"), DEFAULT_VIEW_STATE.pageSize),
    ),
    sort:
      parseEnumValue(searchParams.get("sort"), SORT_VALUES) ?? DEFAULT_VIEW_STATE.sort,
    order:
      parseEnumValue(searchParams.get("order"), ORDER_VALUES) ?? DEFAULT_VIEW_STATE.order,
    search: search.length > 0 ? search : null,
    source: parseEnumValue(searchParams.get("source"), SOURCE_VALUES),
    triageStatus: parseEnumValue(searchParams.get("triageStatus"), TRIAGE_VALUES),
    analysisStatus: parseEnumValue(searchParams.get("analysisStatus"), ANALYSIS_VALUES),
    monetization: parseEnumValue(searchParams.get("monetization"), MONETIZATION_VALUES),
    minStars: parseNonNegativeInt(searchParams.get("minStars")),
    maxStars: parseNonNegativeInt(searchParams.get("maxStars")),
  };
}

export function buildRepositoryCatalogSearchParams(
  state: RepositoryCatalogViewState,
): URLSearchParams {
  const params = new URLSearchParams();

  if (state.page !== DEFAULT_VIEW_STATE.page) {
    params.set("page", String(state.page));
  }
  if (state.pageSize !== DEFAULT_VIEW_STATE.pageSize) {
    params.set("pageSize", String(state.pageSize));
  }
  if (state.sort !== DEFAULT_VIEW_STATE.sort) {
    params.set("sort", state.sort);
  }
  if (state.order !== DEFAULT_VIEW_STATE.order) {
    params.set("order", state.order);
  }
  if (state.search) {
    params.set("search", state.search);
  }
  if (state.source) {
    params.set("source", state.source);
  }
  if (state.triageStatus) {
    params.set("triageStatus", state.triageStatus);
  }
  if (state.analysisStatus) {
    params.set("analysisStatus", state.analysisStatus);
  }
  if (state.monetization) {
    params.set("monetization", state.monetization);
  }
  if (state.minStars !== null) {
    params.set("minStars", String(state.minStars));
  }
  if (state.maxStars !== null) {
    params.set("maxStars", String(state.maxStars));
  }

  return params;
}

export function getRepositoryCatalogQueryKey(state: RepositoryCatalogViewState) {
  return [
    "repositories",
    "catalog",
    state.page,
    state.pageSize,
    state.sort,
    state.order,
    state.search,
    state.source,
    state.triageStatus,
    state.analysisStatus,
    state.monetization,
    state.minStars,
    state.maxStars,
  ] as const;
}

export function getRepositoryCatalogValidationMessage(
  state: RepositoryCatalogViewState,
): string | null {
  if (
    state.minStars !== null &&
    state.maxStars !== null &&
    state.minStars > state.maxStars
  ) {
    return "Minimum stars cannot exceed maximum stars.";
  }

  return null;
}

function buildRepositoryCatalogApiParams(
  state: RepositoryCatalogViewState,
): URLSearchParams {
  const params = new URLSearchParams();
  params.set("page", String(state.page));
  params.set("page_size", String(state.pageSize));
  params.set("sort_by", state.sort);
  params.set("sort_order", state.order);
  if (state.search) {
    params.set("search", state.search);
  }
  if (state.source) {
    params.set("discovery_source", state.source);
  }
  if (state.triageStatus) {
    params.set("triage_status", state.triageStatus);
  }
  if (state.analysisStatus) {
    params.set("analysis_status", state.analysisStatus);
  }
  if (state.monetization) {
    params.set("monetization_potential", state.monetization);
  }
  if (state.minStars !== null) {
    params.set("min_stars", String(state.minStars));
  }
  if (state.maxStars !== null) {
    params.set("max_stars", String(state.maxStars));
  }
  return params;
}

export async function fetchRepositoryCatalog(
  state: RepositoryCatalogViewState,
): Promise<RepositoryCatalogPageResponse> {
  const response = await fetch(
    `${getRequiredApiBaseUrl()}/api/v1/repositories?${buildRepositoryCatalogApiParams(state).toString()}`,
    {
      cache: "no-store",
    },
  );

  if (response.ok) {
    return (await response.json()) as RepositoryCatalogPageResponse;
  }

  let payload: RepositoryCatalogErrorEnvelope | null = null;
  try {
    payload = (await response.json()) as RepositoryCatalogErrorEnvelope;
  } catch {
    payload = null;
  }

  throw new RepositoryCatalogRequestError(
    payload?.error?.message ??
      `Failed to fetch repository catalog: ${response.status} ${response.statusText}`.trim(),
    {
      status: response.status,
      code: payload?.error?.code,
      details: payload?.error?.details,
    },
  );
}

function titleCaseWords(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function describeRepositoryCatalogFilters(
  state: RepositoryCatalogViewState,
): RepositoryCatalogFilterChip[] {
  const chips: RepositoryCatalogFilterChip[] = [];

  if (state.search) {
    chips.push({ key: "search", label: `Search: ${state.search}` });
  }
  if (state.source) {
    chips.push({
      key: "source",
      label: `Source: ${titleCaseWords(state.source)}`,
    });
  }
  if (state.triageStatus) {
    chips.push({
      key: "triageStatus",
      label: `Triage: ${titleCaseWords(state.triageStatus)}`,
    });
  }
  if (state.analysisStatus) {
    chips.push({
      key: "analysisStatus",
      label: `Analysis: ${titleCaseWords(state.analysisStatus)}`,
    });
  }
  if (state.monetization) {
    chips.push({
      key: "monetization",
      label: `Fit: ${titleCaseWords(state.monetization)}`,
    });
  }
  if (state.minStars !== null) {
    chips.push({
      key: "minStars",
      label: `Min Stars: ${state.minStars}`,
    });
  }
  if (state.maxStars !== null) {
    chips.push({
      key: "maxStars",
      label: `Max Stars: ${state.maxStars}`,
    });
  }

  return chips;
}

export function clearRepositoryCatalogFilter(
  state: RepositoryCatalogViewState,
  key: RepositoryCatalogFilterKey,
): RepositoryCatalogViewState {
  const nextState: RepositoryCatalogViewState = {
    ...state,
    page: 1,
  };

  if (key === "search") {
    nextState.search = null;
  }
  if (key === "source") {
    nextState.source = null;
  }
  if (key === "triageStatus") {
    nextState.triageStatus = null;
  }
  if (key === "analysisStatus") {
    nextState.analysisStatus = null;
  }
  if (key === "monetization") {
    nextState.monetization = null;
  }
  if (key === "minStars") {
    nextState.minStars = null;
  }
  if (key === "maxStars") {
    nextState.maxStars = null;
  }

  return nextState;
}

export function clearAllRepositoryCatalogFilters(
  state: RepositoryCatalogViewState,
): RepositoryCatalogViewState {
  return {
    ...state,
    page: 1,
    search: null,
    source: null,
    triageStatus: null,
    analysisStatus: null,
    monetization: null,
    minStars: null,
    maxStars: null,
  };
}

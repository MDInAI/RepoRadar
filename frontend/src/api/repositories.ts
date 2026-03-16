import { getRequiredApiBaseUrl } from "./base-url";

export type RepositoryDiscoverySource = "unknown" | "firehose" | "backfill";
export type RepositoryFirehoseMode = "new" | "trending";
export type RepositoryQueueStatus = "pending" | "in_progress" | "completed" | "failed";
export type RepositoryIntakeStatus = RepositoryQueueStatus;
export type RepositoryTriageStatus = "pending" | "accepted" | "rejected";
export type RepositoryAnalysisStatus = "pending" | "in_progress" | "completed" | "failed";
export type RepositoryMonetizationPotential = "low" | "medium" | "high";
export type RepositoryCategory =
  | "workflow"
  | "analytics"
  | "devops"
  | "infrastructure"
  | "devtools"
  | "crm"
  | "communication"
  | "support"
  | "observability"
  | "low_code"
  | "security"
  | "ai_ml"
  | "data"
  | "productivity";
export type RepositoryCatalogSortBy = "stars" | "forks" | "pushed_at" | "ingested_at";
export type RepositoryCatalogSortOrder = "asc" | "desc";
export type RepositoryTriageExplanationKind =
  | "exclude_rule"
  | "include_rule"
  | "allowlist_miss"
  | "pass_through";

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
  firehose_discovery_mode: RepositoryFirehoseMode | null;
  intake_status: RepositoryIntakeStatus;
  triage_status: RepositoryTriageStatus;
  analysis_status: RepositoryAnalysisStatus;
  queue_created_at: string | null;
  processing_started_at: string | null;
  processing_completed_at: string | null;
  intake_failed_at: string | null;
  analysis_failed_at: string | null;
  failure: RepositoryFailureContext | null;
  category?: RepositoryCategory | null;
  agent_tags?: string[];
  monetization_potential: RepositoryMonetizationPotential | null;
  has_readme_artifact: boolean;
  has_analysis_artifact: boolean;
  is_starred: boolean;
  user_tags: string[];
  idea_family_ids?: number[];
}

export interface RepositoryBacklogSummary {
  queue: {
    pending: number;
    in_progress: number;
    completed: number;
    failed: number;
  };
  triage: {
    pending: number;
    accepted: number;
    rejected: number;
  };
  analysis: {
    pending: number;
    in_progress: number;
    completed: number;
    failed: number;
  };
}

export interface RepositoryCatalogPageResponse {
  items: RepositoryCatalogItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface RepositoryArtifactRef {
  artifact_kind: "readme_snapshot" | "analysis_result";
  runtime_relative_path: string;
  content_sha256: string;
  byte_size: number;
  content_type: string;
  source_kind: string;
  source_url: string | null;
  provenance_metadata: Record<string, unknown>;
  generated_at: string;
}

export interface RepositoryAnalysisSummary {
  monetization_potential: RepositoryMonetizationPotential;
  category?: RepositoryCategory | null;
  category_confidence_score?: number | null;
  analysis_mode?: string | null;
  analysis_outcome?: string | null;
  analysis_schema_version?: string | null;
  analysis_evidence_version?: string | null;
  insufficient_evidence_reason?: string | null;
  evidence_summary?: string | null;
  analysis_signals: Record<string, unknown>;
  score_breakdown: Record<string, number>;
  analysis_summary_short?: string | null;
  analysis_summary_long?: string | null;
  supporting_signals: string[];
  red_flags: string[];
  contradictions: string[];
  missing_information: string[];
  agent_tags?: string[];
  suggested_new_categories: string[];
  suggested_new_tags: string[];
  pros: string[];
  cons: string[];
  missing_feature_signals: string[];
  problem_statement?: string | null;
  target_customer?: string | null;
  product_type?: string | null;
  business_model_guess?: string | null;
  technical_stack?: string | null;
  target_audience?: string | null;
  open_problems?: string | null;
  competitors?: string | null;
  confidence_score?: number | null;
  recommended_action?: string | null;
  source_metadata: Record<string, unknown>;
  analyzed_at: string;
}

export interface RepositoryTriageExplanation {
  kind: RepositoryTriageExplanationKind;
  summary: string;
  matched_include_rules: string[];
  matched_exclude_rules: string[];
  explained_at: string;
}

export interface RepositoryTriageContext {
  triage_status: RepositoryTriageStatus;
  triaged_at: string | null;
  explanation: RepositoryTriageExplanation | null;
}

export interface RepositoryReadmeSnapshot {
  artifact: RepositoryArtifactRef | null;
  content: string | null;
  normalization_version: string | null;
  raw_character_count: number | null;
  normalized_character_count: number | null;
  removed_line_count: number | null;
}

export interface RepositoryAnalysisArtifact {
  artifact: RepositoryArtifactRef | null;
  provider_name: string | null;
  model_name: string | null;
  source_metadata: Record<string, unknown>;
  payload: Record<string, unknown> | null;
}

export interface RepositoryFailureContext {
  stage: string;
  step: string;
  upstream_source: string;
  error_code: string | null;
  error_message: string | null;
  failed_at: string | null;
}

export interface RepositoryProcessingContext {
  intake_created_at: string | null;
  intake_started_at: string | null;
  intake_completed_at: string | null;
  intake_failed_at: string | null;
  triaged_at: string | null;
  analysis_started_at: string | null;
  analysis_completed_at: string | null;
  analysis_last_attempted_at: string | null;
  analysis_failed_at: string | null;
  failure: RepositoryFailureContext | null;
}

export interface RepositoryDetailResponse {
  github_repository_id: number;
  source_provider: string;
  owner_login: string;
  repository_name: string;
  full_name: string;
  repository_description: string | null;
  discovery_source: RepositoryDiscoverySource;
  firehose_discovery_mode: RepositoryFirehoseMode | null;
  intake_status: RepositoryIntakeStatus;
  triage_status: RepositoryTriageStatus;
  analysis_status: RepositoryAnalysisStatus;
  stargazers_count: number;
  forks_count: number;
  github_created_at: string | null;
  discovered_at: string;
  status_updated_at: string;
  pushed_at: string | null;
  category?: RepositoryCategory | null;
  agent_tags?: string[];
  triage: RepositoryTriageContext;
  analysis_summary: RepositoryAnalysisSummary | null;
  readme_snapshot: RepositoryReadmeSnapshot | null;
  analysis_artifact: RepositoryAnalysisArtifact | null;
  artifacts: RepositoryArtifactRef[];
  processing: RepositoryProcessingContext;
  has_readme_artifact: boolean;
  has_analysis_artifact: boolean;
  is_starred: boolean;
  user_tags: string[];
  idea_family_ids: number[];
}

export interface RepositoryCurationState {
  is_starred: boolean;
  starred_at: string | null;
  user_tags: string[];
}

export interface RepositoryUserTagResponse {
  tag_label: string;
  created_at: string;
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
  queueStatus: RepositoryQueueStatus | null;
  triageStatus: RepositoryTriageStatus | null;
  analysisStatus: RepositoryAnalysisStatus | null;
  hasFailures: boolean;
  category: RepositoryCategory | null;
  agentTag: string | null;
  userTag: string | null;
  monetization: RepositoryMonetizationPotential | null;
  minStars: number | null;
  maxStars: number | null;
  starredOnly: boolean;
  ideaFamilyId: number | null;
}

export type RepositoryCatalogFilterKey =
  | "search"
  | "source"
  | "queueStatus"
  | "triageStatus"
  | "analysisStatus"
  | "hasFailures"
  | "category"
  | "agentTag"
  | "userTag"
  | "monetization"
  | "minStars"
  | "maxStars"
  | "starredOnly";

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
  queueStatus: null,
  triageStatus: null,
  analysisStatus: null,
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

const SOURCE_VALUES: RepositoryDiscoverySource[] = ["unknown", "firehose", "backfill"];
const QUEUE_VALUES: RepositoryQueueStatus[] = ["pending", "in_progress", "completed", "failed"];
const TRIAGE_VALUES: RepositoryTriageStatus[] = ["pending", "accepted", "rejected"];
const ANALYSIS_VALUES: RepositoryAnalysisStatus[] = [
  "pending",
  "in_progress",
  "completed",
  "failed",
];
const MONETIZATION_VALUES: RepositoryMonetizationPotential[] = ["low", "medium", "high"];
const CATEGORY_VALUES: RepositoryCategory[] = [
  "workflow",
  "analytics",
  "devops",
  "infrastructure",
  "devtools",
  "crm",
  "communication",
  "support",
  "observability",
  "low_code",
  "security",
  "ai_ml",
  "data",
  "productivity",
];
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

export class RepositoryDetailRequestError extends Error {
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
    this.name = "RepositoryDetailRequestError";
    this.status = options.status;
    this.code = options.code;
    this.details = options.details ?? {};
  }
}

export class RepositoryCurationRequestError extends Error {
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
    this.name = "RepositoryCurationRequestError";
    this.status = options.status;
    this.code = options.code;
    this.details = options.details ?? {};
  }
}

function buildRepositoryNetworkErrorMessage(action: string): string {
  return `${action} failed because the backend API could not be reached at ${getRequiredApiBaseUrl()}. Make sure the backend server is running and NEXT_PUBLIC_API_URL is correct.`;
}

function buildNetworkErrorDetails(error: unknown): Record<string, unknown> {
  return {
    api_base_url: getRequiredApiBaseUrl(),
    cause: error instanceof Error ? error.message : String(error),
  };
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

function parseBooleanParam(value: string | null): boolean {
  return value === "true";
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
    queueStatus: parseEnumValue(searchParams.get("queueStatus"), QUEUE_VALUES),
    triageStatus: parseEnumValue(searchParams.get("triageStatus"), TRIAGE_VALUES),
    analysisStatus: parseEnumValue(searchParams.get("analysisStatus"), ANALYSIS_VALUES),
    hasFailures: parseBooleanParam(searchParams.get("hasFailures")),
    category: parseEnumValue(searchParams.get("category"), CATEGORY_VALUES),
    agentTag: searchParams.get("agentTag")?.trim().toLowerCase() || null,
    userTag: searchParams.get("userTag")?.trim() || null,
    monetization: parseEnumValue(searchParams.get("monetization"), MONETIZATION_VALUES),
    minStars: parseNonNegativeInt(searchParams.get("minStars")),
    maxStars: parseNonNegativeInt(searchParams.get("maxStars")),
    starredOnly: parseBooleanParam(searchParams.get("starredOnly")),
    ideaFamilyId: parseNonNegativeInt(searchParams.get("ideaFamilyId")),
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
  if (state.queueStatus) {
    params.set("queueStatus", state.queueStatus);
  }
  if (state.triageStatus) {
    params.set("triageStatus", state.triageStatus);
  }
  if (state.analysisStatus) {
    params.set("analysisStatus", state.analysisStatus);
  }
  if (state.hasFailures) {
    params.set("hasFailures", "true");
  }
  if (state.category) {
    params.set("category", state.category);
  }
  if (state.agentTag) {
    params.set("agentTag", state.agentTag);
  }
  if (state.userTag) {
    params.set("userTag", state.userTag);
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
  if (state.starredOnly) {
    params.set("starredOnly", "true");
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
    state.queueStatus,
    state.triageStatus,
    state.analysisStatus,
    state.hasFailures,
    state.category,
    state.agentTag,
    state.userTag,
    state.monetization,
    state.minStars,
    state.maxStars,
    state.starredOnly,
  ] as const;
}

export function getRepositoryDetailQueryKey(repositoryId: number) {
  return ["repositories", "detail", repositoryId] as const;
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
  if (state.queueStatus) {
    params.set("queue_status", state.queueStatus);
  }
  if (state.triageStatus) {
    params.set("triage_status", state.triageStatus);
  }
  if (state.analysisStatus) {
    params.set("analysis_status", state.analysisStatus);
  }
  if (state.hasFailures) {
    params.set("has_failures", "true");
  }
  if (state.category) {
    params.set("category", state.category);
  }
  if (state.agentTag) {
    params.set("agent_tag", state.agentTag);
  }
  if (state.userTag) {
    params.set("user_tag", state.userTag);
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
  if (state.starredOnly) {
    params.set("starred_only", "true");
  }
  if (state.ideaFamilyId !== null) {
    params.set("idea_family_id", String(state.ideaFamilyId));
  }
  return params;
}

export async function fetchRepositoryCatalog(
  state: RepositoryCatalogViewState,
): Promise<RepositoryCatalogPageResponse> {
  let response: Response;
  try {
    response = await fetch(
      `${getRequiredApiBaseUrl()}/api/v1/repositories?${buildRepositoryCatalogApiParams(state).toString()}`,
      {
        cache: "no-store",
      },
    );
  } catch (error) {
    throw new RepositoryCatalogRequestError(
      buildRepositoryNetworkErrorMessage("Repository catalog request"),
      {
        status: 0,
        code: "network_error",
        details: buildNetworkErrorDetails(error),
      },
    );
  }

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

export function getRepositoryBacklogSummaryQueryKey() {
  return ["repositories", "backlog-summary"] as const;
}

export async function fetchRepositoryBacklogSummary(): Promise<RepositoryBacklogSummary> {
  let response: Response;
  try {
    response = await fetch(
      `${getRequiredApiBaseUrl()}/api/v1/repositories/backlog/summary`,
      {
        cache: "no-store",
      },
    );
  } catch (error) {
    throw new RepositoryCatalogRequestError(
      buildRepositoryNetworkErrorMessage("Repository backlog request"),
      {
        status: 0,
        code: "network_error",
        details: buildNetworkErrorDetails(error),
      },
    );
  }

  if (response.ok) {
    return (await response.json()) as RepositoryBacklogSummary;
  }

  let payload: RepositoryCatalogErrorEnvelope | null = null;
  try {
    payload = (await response.json()) as RepositoryCatalogErrorEnvelope;
  } catch {
    payload = null;
  }

  throw new RepositoryCatalogRequestError(
    payload?.error?.message ??
      `Failed to fetch repository backlog summary: ${response.status} ${response.statusText}`.trim(),
    {
      status: response.status,
      code: payload?.error?.code,
      details: payload?.error?.details,
    },
  );
}

export async function fetchRepositoryDetail(
  repositoryId: number,
): Promise<RepositoryDetailResponse> {
  let response: Response;
  try {
    response = await fetch(
      `${getRequiredApiBaseUrl()}/api/v1/repositories/${repositoryId}`,
      {
        cache: "no-store",
      },
    );
  } catch (error) {
    throw new RepositoryDetailRequestError(
      buildRepositoryNetworkErrorMessage("Repository detail request"),
      {
        status: 0,
        code: "network_error",
        details: buildNetworkErrorDetails(error),
      },
    );
  }

  if (response.ok) {
    return (await response.json()) as RepositoryDetailResponse;
  }

  let payload: RepositoryCatalogErrorEnvelope | null = null;
  try {
    payload = (await response.json()) as RepositoryCatalogErrorEnvelope;
  } catch {
    payload = null;
  }

  throw new RepositoryDetailRequestError(
    payload?.error?.message ??
      `Failed to fetch repository detail: ${response.status} ${response.statusText}`.trim(),
    {
      status: response.status,
      code: payload?.error?.code,
      details: payload?.error?.details,
    },
  );
}

export async function updateRepositoryStar(
  repositoryId: number,
  starred: boolean,
): Promise<RepositoryCurationState> {
  let response: Response;
  try {
    response = await fetch(
      `${getRequiredApiBaseUrl()}/api/v1/repositories/${repositoryId}/star`,
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ starred }),
      },
    );
  } catch (error) {
    throw new RepositoryCurationRequestError(
      buildRepositoryNetworkErrorMessage("Repository star update"),
      {
        status: 0,
        code: "network_error",
        details: buildNetworkErrorDetails(error),
      },
    );
  }

  if (response.ok) {
    return (await response.json()) as RepositoryCurationState;
  }

  let payload: RepositoryCatalogErrorEnvelope | null = null;
  try {
    payload = (await response.json()) as RepositoryCatalogErrorEnvelope;
  } catch {
    payload = null;
  }

  throw new RepositoryCurationRequestError(
    payload?.error?.message ??
      `Failed to update repository star state: ${response.status} ${response.statusText}`.trim(),
    {
      status: response.status,
      code: payload?.error?.code,
      details: payload?.error?.details,
    },
  );
}

export async function addRepositoryUserTag(
  repositoryId: number,
  tagLabel: string,
): Promise<RepositoryUserTagResponse> {
  let response: Response;
  try {
    response = await fetch(
      `${getRequiredApiBaseUrl()}/api/v1/repositories/${repositoryId}/tags`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ tag_label: tagLabel }),
      },
    );
  } catch (error) {
    throw new RepositoryCurationRequestError(
      buildRepositoryNetworkErrorMessage("Repository tag creation"),
      {
        status: 0,
        code: "network_error",
        details: buildNetworkErrorDetails(error),
      },
    );
  }

  if (response.ok) {
    return (await response.json()) as RepositoryUserTagResponse;
  }

  let payload: RepositoryCatalogErrorEnvelope | null = null;
  try {
    payload = (await response.json()) as RepositoryCatalogErrorEnvelope;
  } catch {
    payload = null;
  }

  throw new RepositoryCurationRequestError(
    payload?.error?.message ??
      `Failed to add repository tag: ${response.status} ${response.statusText}`.trim(),
    {
      status: response.status,
      code: payload?.error?.code,
      details: payload?.error?.details,
    },
  );
}

export async function removeRepositoryUserTag(
  repositoryId: number,
  tagLabel: string,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(
      `${getRequiredApiBaseUrl()}/api/v1/repositories/${repositoryId}/tags/${encodeURIComponent(tagLabel)}`,
      {
        method: "DELETE",
      },
    );
  } catch (error) {
    throw new RepositoryCurationRequestError(
      buildRepositoryNetworkErrorMessage("Repository tag removal"),
      {
        status: 0,
        code: "network_error",
        details: buildNetworkErrorDetails(error),
      },
    );
  }

  if (response.status === 204) {
    return;
  }

  let payload: RepositoryCatalogErrorEnvelope | null = null;
  try {
    payload = (await response.json()) as RepositoryCatalogErrorEnvelope;
  } catch {
    payload = null;
  }

  throw new RepositoryCurationRequestError(
    payload?.error?.message ??
      `Failed to remove repository tag: ${response.status} ${response.statusText}`.trim(),
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
  if (state.queueStatus) {
    chips.push({
      key: "queueStatus",
      label: `Queue: ${titleCaseWords(state.queueStatus)}`,
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
  if (state.hasFailures) {
    chips.push({
      key: "hasFailures",
      label: "Failures only",
    });
  }
  if (state.category) {
    chips.push({
      key: "category",
      label: `Category: ${titleCaseWords(state.category)}`,
    });
  }
  if (state.agentTag) {
    chips.push({
      key: "agentTag",
      label: `Agent Tag: ${state.agentTag}`,
    });
  }
  if (state.userTag) {
    chips.push({
      key: "userTag",
      label: `User Tag: ${state.userTag}`,
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
  if (state.starredOnly) {
    chips.push({
      key: "starredOnly",
      label: "Starred only",
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
  if (key === "queueStatus") {
    nextState.queueStatus = null;
  }
  if (key === "triageStatus") {
    nextState.triageStatus = null;
  }
  if (key === "analysisStatus") {
    nextState.analysisStatus = null;
  }
  if (key === "hasFailures") {
    nextState.hasFailures = false;
  }
  if (key === "category") {
    nextState.category = null;
  }
  if (key === "agentTag") {
    nextState.agentTag = null;
  }
  if (key === "userTag") {
    nextState.userTag = null;
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
  if (key === "starredOnly") {
    nextState.starredOnly = false;
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
    queueStatus: null,
    triageStatus: null,
    analysisStatus: null,
    hasFailures: false,
    category: null,
    agentTag: null,
    userTag: null,
    monetization: null,
    minStars: null,
    maxStars: null,
    starredOnly: false,
  };
}

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import RepositoriesDetailPage from "@/app/repositories/[repositoryId]/page";

const detailResponse = {
  github_repository_id: 701,
  source_provider: "github",
  owner_login: "alpha",
  repository_name: "growth-engine",
  full_name: "alpha/growth-engine",
  repository_description: "Growth workflows for operators",
  discovery_source: "firehose",
  firehose_discovery_mode: "trending",
  intake_status: "completed",
  triage_status: "accepted",
  analysis_status: "completed",
  stargazers_count: 900,
  forks_count: 90,
  discovered_at: "2026-03-09T12:00:00Z",
  status_updated_at: "2026-03-09T12:00:00Z",
  pushed_at: "2026-03-09T12:00:00Z",
  category: "workflow",
  agent_tags: ["workflow", "approval"],
  triage: {
    triage_status: "accepted",
    triaged_at: "2026-03-09T12:00:00Z",
    explanation: {
      kind: "include_rule",
      summary: "Accepted because workflow automation matched the include set.",
      matched_include_rules: ["workflow", "automation"],
      matched_exclude_rules: [],
      explained_at: "2026-03-09T12:00:00Z",
    },
  },
  analysis_summary: {
    monetization_potential: "high",
    category: "workflow",
    agent_tags: ["workflow", "approval"],
    pros: ["Clear workflow"],
    cons: ["Pricing unknown"],
    missing_feature_signals: ["Missing SSO"],
    source_metadata: {
      readme_artifact_path: "data/readmes/701.md",
      analysis_artifact_path: "data/analyses/701.json",
      analysis_provider: "StaticAnalysisProvider",
    },
    analyzed_at: "2026-03-09T12:05:00Z",
  },
  readme_snapshot: {
    artifact: {
      artifact_kind: "readme_snapshot",
      runtime_relative_path: "data/readmes/701.md",
      content_sha256: "a".repeat(64),
      byte_size: 128,
      content_type: "text/markdown; charset=utf-8",
      source_kind: "repository_readme",
      source_url: "https://api.github.com/repos/alpha/growth-engine/readme",
      provenance_metadata: {
        normalization_version: "story-3.4-v1",
        raw_character_count: 2400,
        normalized_character_count: 1040,
        removed_line_count: 10,
      },
      generated_at: "2026-03-09T12:00:00Z",
    },
    content: "# Growth Engine\n\nWorkflow automation with analytics.",
    normalization_version: "story-3.4-v1",
    raw_character_count: 2400,
    normalized_character_count: 1040,
    removed_line_count: 10,
  },
  analysis_artifact: {
    artifact: {
      artifact_kind: "analysis_result",
      runtime_relative_path: "data/analyses/701.json",
      content_sha256: "b".repeat(64),
      byte_size: 256,
      content_type: "application/json",
      source_kind: "repository_analysis",
      source_url: "https://api.github.com/repos/alpha/growth-engine/readme",
      provenance_metadata: {
        analysis_provider: "StaticAnalysisProvider",
      },
      generated_at: "2026-03-09T12:05:00Z",
    },
    provider_name: "StaticAnalysisProvider",
    source_metadata: {
      readme_artifact_path: "data/readmes/701.md",
      analysis_artifact_path: "data/analyses/701.json",
      analysis_provider: "StaticAnalysisProvider",
    },
    payload: {
      schema_version: "story-3.4-v1",
      github_repository_id: 701,
      analysis: {
        monetization_potential: "high",
        pros: ["Clear workflow"],
        cons: ["Pricing unknown"],
        missing_feature_signals: ["Missing SSO"],
      },
    },
  },
  artifacts: [
    {
      artifact_kind: "analysis_result",
      runtime_relative_path: "data/analyses/701.json",
      content_sha256: "b".repeat(64),
      byte_size: 256,
      content_type: "application/json",
      source_kind: "repository_analysis",
      source_url: "https://api.github.com/repos/alpha/growth-engine/readme",
      provenance_metadata: {
        analysis_provider: "StaticAnalysisProvider",
      },
      generated_at: "2026-03-09T12:05:00Z",
    },
    {
      artifact_kind: "readme_snapshot",
      runtime_relative_path: "data/readmes/701.md",
      content_sha256: "a".repeat(64),
      byte_size: 128,
      content_type: "text/markdown; charset=utf-8",
      source_kind: "repository_readme",
      source_url: "https://api.github.com/repos/alpha/growth-engine/readme",
      provenance_metadata: {
        normalization_version: "story-3.4-v1",
      },
      generated_at: "2026-03-09T12:00:00Z",
    },
  ],
  processing: {
    intake_created_at: "2026-03-09T12:00:00Z",
    intake_started_at: "2026-03-09T12:01:00Z",
    intake_completed_at: "2026-03-09T12:02:00Z",
    intake_failed_at: null,
    triaged_at: "2026-03-09T12:00:00Z",
    analysis_started_at: "2026-03-09T12:03:00Z",
    analysis_completed_at: "2026-03-09T12:05:00Z",
    analysis_last_attempted_at: "2026-03-09T12:05:00Z",
    analysis_failed_at: null,
    failure: null,
  },
  has_readme_artifact: true,
  has_analysis_artifact: true,
  is_starred: false,
  user_tags: ["workflow"],
};

async function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(detailResponse), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
      },
    }),
  );

  const page = await RepositoriesDetailPage({
    params: Promise.resolve({ repositoryId: "701" }),
  });

  return render(
    <QueryClientProvider client={queryClient}>
      {page}
    </QueryClientProvider>,
  );
}

describe("Repository detail page", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://api.test";
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  test("renders the dossier sections and distinguishes raw source from generated analysis", async () => {
    await renderPage();

    expect(await screen.findByRole("heading", { name: "alpha/growth-engine" })).toBeTruthy();
    expect(screen.getByText("README Intelligence")).toBeTruthy();
    expect(screen.getByText("Analyst Output")).toBeTruthy();
    expect(screen.getByText("Analyst Summary")).toBeTruthy();
    expect(screen.getByText("Decision Summary")).toBeTruthy();
    expect(screen.getByText("Tags & Categories")).toBeTruthy();
    expect(screen.getByText("Add to Family")).toBeTruthy();
    expect(screen.getByText("Create Combiner Brief")).toBeTruthy();
    expect(screen.getByText("Similar-Project Scan")).toBeTruthy();
    expect(screen.getByText("User Tags")).toBeTruthy();
    expect(screen.getAllByText("workflow").length).toBeGreaterThan(0);
  });

  test("renders granular failure context when repository processing fails", async () => {
    const failedDetail = {
      ...detailResponse,
      intake_status: "completed",
      analysis_status: "failed",
      processing: {
        ...detailResponse.processing,
        analysis_failed_at: "2026-03-09T12:07:00Z",
        failure: {
          stage: "analysis",
          step: "analysis",
          upstream_source: "firehose",
          error_code: "rate_limited",
          error_message: "Gateway rate limit while analyzing repository.",
          failed_at: "2026-03-09T12:07:00Z",
        },
      },
    };

    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(failedDetail), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      }),
    );

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    const page = await RepositoriesDetailPage({
      params: Promise.resolve({ repositoryId: "701" }),
    });

    render(<QueryClientProvider client={queryClient}>{page}</QueryClientProvider>);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "History" }));

    expect(await screen.findByText("Active failure context")).toBeTruthy();
    expect(screen.getByText("Analysis failure at Analysis")).toBeTruthy();
    expect(screen.getByText("Error: Gateway rate limit while analyzing repository.")).toBeTruthy();
    expect(screen.getByText("Recorded at: 2026-03-09 12:07 UTC")).toBeTruthy();
  });

  test("does not invent failure context when the backend omits it", async () => {
    const failedDetail = {
      ...detailResponse,
      intake_status: "failed",
      analysis_status: "pending",
      processing: {
        ...detailResponse.processing,
        intake_failed_at: "2026-03-09T12:07:00Z",
        failure: null,
      },
    };

    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(failedDetail), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      }),
    );

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    const page = await RepositoriesDetailPage({
      params: Promise.resolve({ repositoryId: "701" }),
    });

    render(<QueryClientProvider client={queryClient}>{page}</QueryClientProvider>);

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "History" }));

    expect(await screen.findByText("No repository processing failure is currently recorded.")).toBeTruthy();
    expect(screen.queryByText("Active failure context")).toBeNull();
  });

  test("surfaces explicit action context for scaffolded actions", async () => {
    const user = userEvent.setup();
    await renderPage();

    await user.click(await screen.findByRole("button", { name: "Stage family assignment" }));

    await waitFor(() => {
      expect(screen.getByText("What Happens")).toBeTruthy();
    });

    expect(screen.getAllByText("alpha/growth-engine").length).toBeGreaterThan(0);
    expect(screen.getByText("Selected")).toBeTruthy();
    expect(screen.getAllByText("Ideas > Family Workspace").length).toBeGreaterThan(0);
    expect(screen.getByText("Expected Result")).toBeTruthy();
  });
});

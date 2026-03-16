import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

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
import { CatalogFilterBar } from "@/components/repositories/CatalogFilterBar";

interface CatalogFilterBarProps {
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
}

function renderFilterBar(overrides: Partial<CatalogFilterBarProps> = {}) {
  const props: CatalogFilterBarProps = {
    searchValue: "",
    source: null,
    category: null,
    agentTag: null,
    userTag: null,
    queueStatus: null,
    triageStatus: null,
    analysisStatus: null,
    hasFailures: false,
    monetization: null,
    minStars: null,
    maxStars: null,
    starredOnly: false,
    sort: "stars",
    order: "desc",
    visibleCount: 1,
    totalCount: 10,
    chips: [],
    isRefreshing: false,
    validationMessage: null,
    onSearchChange: vi.fn(),
    onSourceChange: vi.fn(),
    onCategoryChange: vi.fn(),
    onAgentTagChange: vi.fn(),
    onUserTagChange: vi.fn(),
    onQueueStatusChange: vi.fn(),
    onTriageStatusChange: vi.fn(),
    onAnalysisStatusChange: vi.fn(),
    onHasFailuresChange: vi.fn(),
    onMonetizationChange: vi.fn(),
    onMinStarsChange: vi.fn(),
    onMaxStarsChange: vi.fn(),
    onStarredOnlyChange: vi.fn(),
    onSortChange: vi.fn(),
    onOrderChange: vi.fn(),
    onRemoveChip: vi.fn(),
    onClearAll: vi.fn(),
    ...overrides,
  };

  render(<CatalogFilterBar {...props} />);
  return props;
}

describe("CatalogFilterBar", () => {
  afterEach(() => {
    cleanup();
  });

  test("renders the filter toolbar, empty-chip state, and dropdown options", () => {
    renderFilterBar();

    expect(screen.getByPlaceholderText("Search name or description")).toBeTruthy();
    expect(screen.getByText("No active filters")).toBeTruthy();
    expect(screen.getByText("Showing 1 of 10 repos")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Toggle sort order" }).textContent).toContain(
      "High to low",
    );

    expect(screen.getByRole("option", { name: "All sources" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "Backfill" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "All categories" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "All queue" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "All triage" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "Accepted" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "All analysis" })).toBeTruthy();
    expect(screen.getAllByRole("option", { name: "Completed" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("option", { name: "All fit scores" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "Medium" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "Added to website" })).toBeTruthy();
  });

  test("dispatches every control handler and chip action", async () => {
    const user = userEvent.setup();
    const props = renderFilterBar({
      chips: [
        { key: "search", label: "Search: growth" },
        { key: "source", label: "Source: Firehose" },
      ],
      isRefreshing: true,
    });

    expect(screen.getByText("Refreshing")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Search repositories"), {
      target: { value: "growth" },
    });
    expect(props.onSearchChange).toHaveBeenLastCalledWith("growth");

    fireEvent.change(screen.getByLabelText("Agent tag"), {
      target: { value: "workflow" },
    });
    expect(props.onAgentTagChange).toHaveBeenCalledWith("workflow");

    fireEvent.change(screen.getByLabelText("User tag"), {
      target: { value: "priority" },
    });
    expect(props.onUserTagChange).toHaveBeenCalledWith("priority");

    await user.selectOptions(screen.getByLabelText("Discovery source"), "firehose");
    expect(props.onSourceChange).toHaveBeenCalledWith("firehose");

    await user.selectOptions(screen.getByLabelText("Category"), "analytics");
    expect(props.onCategoryChange).toHaveBeenCalledWith("analytics");

    await user.selectOptions(screen.getByLabelText("Queue status"), "failed");
    expect(props.onQueueStatusChange).toHaveBeenCalledWith("failed");

    await user.selectOptions(screen.getByLabelText("Triage status"), "accepted");
    expect(props.onTriageStatusChange).toHaveBeenCalledWith("accepted");

    await user.selectOptions(screen.getByLabelText("Analysis status"), "completed");
    expect(props.onAnalysisStatusChange).toHaveBeenCalledWith("completed");

    await user.selectOptions(screen.getByLabelText("Monetization fit"), "high");
    expect(props.onMonetizationChange).toHaveBeenCalledWith("high");

    await user.selectOptions(screen.getByLabelText("Sort by"), "forks");
    expect(props.onSortChange).toHaveBeenCalledWith("forks");

    await user.click(screen.getByRole("button", { name: "Toggle sort order" }));
    expect(props.onOrderChange).toHaveBeenCalledWith("asc");

    fireEvent.change(screen.getByLabelText("Minimum stars"), {
      target: { value: "75" },
    });
    expect(props.onMinStarsChange).toHaveBeenLastCalledWith(75);

    fireEvent.change(screen.getByLabelText("Maximum stars"), {
      target: { value: "125" },
    });
    expect(props.onMaxStarsChange).toHaveBeenLastCalledWith(125);

    await user.click(screen.getByLabelText("Show starred only"));
    expect(props.onStarredOnlyChange).toHaveBeenCalledWith(true);

    await user.click(screen.getByLabelText("Show failures only"));
    expect(props.onHasFailuresChange).toHaveBeenCalledWith(true);

    await user.click(screen.getByLabelText("Remove Search: growth filter"));
    expect(props.onRemoveChip).toHaveBeenCalledWith("search");

    await user.click(screen.getByRole("button", { name: "Clear all" }));
    expect(props.onClearAll).toHaveBeenCalledOnce();
  });

  test("renders a client-side validation message for invalid star ranges", () => {
    renderFilterBar({
      minStars: 500,
      maxStars: 400,
      validationMessage: "Minimum stars cannot exceed maximum stars.",
    });

    expect(screen.getByText("Minimum stars cannot exceed maximum stars.")).toBeTruthy();
  });
});

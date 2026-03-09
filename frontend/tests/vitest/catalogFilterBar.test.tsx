import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import type {
  RepositoryAnalysisStatus,
  RepositoryCatalogFilterChip,
  RepositoryCatalogSortBy,
  RepositoryCatalogSortOrder,
  RepositoryDiscoverySource,
  RepositoryMonetizationPotential,
  RepositoryTriageStatus,
} from "@/api/repositories";
import { CatalogFilterBar } from "@/components/repositories/CatalogFilterBar";

interface CatalogFilterBarProps {
  searchValue: string;
  source: RepositoryDiscoverySource | null;
  triageStatus: RepositoryTriageStatus | null;
  analysisStatus: RepositoryAnalysisStatus | null;
  monetization: RepositoryMonetizationPotential | null;
  minStars: number | null;
  maxStars: number | null;
  sort: RepositoryCatalogSortBy;
  order: RepositoryCatalogSortOrder;
  visibleCount: number;
  totalCount: number;
  chips: RepositoryCatalogFilterChip[];
  isRefreshing: boolean;
  validationMessage: string | null;
  onSearchChange: (value: string) => void;
  onSourceChange: (value: RepositoryDiscoverySource | null) => void;
  onTriageStatusChange: (value: RepositoryTriageStatus | null) => void;
  onAnalysisStatusChange: (value: RepositoryAnalysisStatus | null) => void;
  onMonetizationChange: (value: RepositoryMonetizationPotential | null) => void;
  onMinStarsChange: (value: number | null) => void;
  onMaxStarsChange: (value: number | null) => void;
  onSortChange: (value: RepositoryCatalogSortBy) => void;
  onOrderChange: (value: RepositoryCatalogSortOrder) => void;
  onRemoveChip: (key: RepositoryCatalogFilterChip["key"]) => void;
  onClearAll: () => void;
}

function renderFilterBar(overrides: Partial<CatalogFilterBarProps> = {}) {
  const props: CatalogFilterBarProps = {
    searchValue: "",
    source: null,
    triageStatus: null,
    analysisStatus: null,
    monetization: null,
    minStars: null,
    maxStars: null,
    sort: "stars",
    order: "desc",
    visibleCount: 1,
    totalCount: 10,
    chips: [],
    isRefreshing: false,
    validationMessage: null,
    onSearchChange: vi.fn(),
    onSourceChange: vi.fn(),
    onTriageStatusChange: vi.fn(),
    onAnalysisStatusChange: vi.fn(),
    onMonetizationChange: vi.fn(),
    onMinStarsChange: vi.fn(),
    onMaxStarsChange: vi.fn(),
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
      "Descending",
    );

    expect(screen.getByRole("option", { name: "All Sources" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "Backfill" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "All Triage" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "Accepted" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "All Analysis" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "Completed" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "All Fit Scores" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "Medium" })).toBeTruthy();
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

    await user.selectOptions(screen.getByLabelText("Discovery source"), "firehose");
    expect(props.onSourceChange).toHaveBeenCalledWith("firehose");

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

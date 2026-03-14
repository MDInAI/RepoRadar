import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FamilyDetailView } from "@/components/ideas/FamilyDetailView";

vi.mock("@/hooks/useIdeaFamilies", () => ({
  useIdeaFamily: vi.fn(),
  useRemoveRepositoryFromFamily: vi.fn(),
}));

vi.mock("@/api/repositories", () => ({
  fetchRepositoryCatalog: vi.fn(),
}));

const { useIdeaFamily, useRemoveRepositoryFromFamily } = await import("@/hooks/useIdeaFamilies");

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("FamilyDetailView", () => {
  it("shows loading state", () => {
    vi.mocked(useIdeaFamily).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as any);

    vi.mocked(useRemoveRepositoryFromFamily).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as any);

    renderWithQuery(
      <FamilyDetailView
        familyId={1}
        onEditFamily={vi.fn()}
        onDeleteFamily={vi.fn()}
        onAddRepositories={vi.fn()}
      />
    );

    expect(screen.getByText("Loading family details...")).toBeInTheDocument();
  });

  it("shows error state", () => {
    vi.mocked(useIdeaFamily).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to load"),
    } as any);

    vi.mocked(useRemoveRepositoryFromFamily).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as any);

    renderWithQuery(
      <FamilyDetailView
        familyId={1}
        onEditFamily={vi.fn()}
        onDeleteFamily={vi.fn()}
        onAddRepositories={vi.fn()}
      />
    );

    expect(screen.getByText("Failed to load family details")).toBeInTheDocument();
  });

  it("renders family details", () => {
    vi.mocked(useIdeaFamily).mockReturnValue({
      data: {
        id: 1,
        title: "Test Family",
        description: "Test description",
        member_count: 0,
        member_repository_ids: [],
        created_at: "2026-03-12T00:00:00Z",
        updated_at: "2026-03-12T00:00:00Z",
      },
      isLoading: false,
      error: null,
    } as any);

    vi.mocked(useRemoveRepositoryFromFamily).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as any);

    renderWithQuery(
      <FamilyDetailView
        familyId={1}
        onEditFamily={vi.fn()}
        onDeleteFamily={vi.fn()}
        onAddRepositories={vi.fn()}
      />
    );

    expect(screen.getByText("Test Family")).toBeInTheDocument();
    expect(screen.getByText("Test description")).toBeInTheDocument();
  });
});

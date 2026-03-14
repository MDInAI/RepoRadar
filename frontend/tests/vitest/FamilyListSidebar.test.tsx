import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FamilyListSidebar } from "@/components/ideas/FamilyListSidebar";

vi.mock("@/hooks/useIdeaFamilies", () => ({
  useIdeaFamilies: vi.fn(),
}));

const { useIdeaFamilies } = await import("@/hooks/useIdeaFamilies");

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("FamilyListSidebar", () => {
  it("shows loading state", () => {
    vi.mocked(useIdeaFamilies).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as any);

    renderWithQuery(
      <FamilyListSidebar
        selectedFamilyId={null}
        onSelectFamily={vi.fn()}
        onCreateFamily={vi.fn()}
      />
    );

    expect(screen.getByText("Loading families...")).toBeInTheDocument();
  });

  it("shows empty state when no families exist", () => {
    vi.mocked(useIdeaFamilies).mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    } as any);

    renderWithQuery(
      <FamilyListSidebar
        selectedFamilyId={null}
        onSelectFamily={vi.fn()}
        onCreateFamily={vi.fn()}
      />
    );

    expect(screen.getByText("No families yet")).toBeInTheDocument();
  });

  it("renders family list", () => {
    vi.mocked(useIdeaFamilies).mockReturnValue({
      data: [
        {
          id: 1,
          title: "Test Family",
          description: "Test description",
          member_count: 5,
          created_at: "2026-03-12T00:00:00Z",
          updated_at: "2026-03-12T00:00:00Z",
        },
      ],
      isLoading: false,
      error: null,
    } as any);

    renderWithQuery(
      <FamilyListSidebar
        selectedFamilyId={null}
        onSelectFamily={vi.fn()}
        onCreateFamily={vi.fn()}
      />
    );

    expect(screen.getByText("Test Family")).toBeInTheDocument();
    expect(screen.getByText("5 repositories")).toBeInTheDocument();
  });
});

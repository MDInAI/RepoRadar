import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FamilyFormDialog } from "@/components/ideas/FamilyFormDialog";

vi.mock("@/hooks/useIdeaFamilies", () => ({
  useCreateIdeaFamily: vi.fn(),
  useUpdateIdeaFamily: vi.fn(),
}));

const { useCreateIdeaFamily, useUpdateIdeaFamily } = await import("@/hooks/useIdeaFamilies");

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("FamilyFormDialog", () => {
  it("does not render when closed", () => {
    vi.mocked(useCreateIdeaFamily).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    } as any);

    vi.mocked(useUpdateIdeaFamily).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    } as any);

    renderWithQuery(
      <FamilyFormDialog
        isOpen={false}
        onClose={vi.fn()}
        family={null}
      />
    );

    expect(screen.queryByText("Create Family")).not.toBeInTheDocument();
  });

  it("renders create mode", () => {
    vi.mocked(useCreateIdeaFamily).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    } as any);

    vi.mocked(useUpdateIdeaFamily).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    } as any);

    renderWithQuery(
      <FamilyFormDialog
        isOpen={true}
        onClose={vi.fn()}
        family={null}
      />
    );

    expect(screen.getByText("Create Family")).toBeInTheDocument();
  });

  it("renders edit mode", () => {
    vi.mocked(useCreateIdeaFamily).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    } as any);

    vi.mocked(useUpdateIdeaFamily).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    } as any);

    renderWithQuery(
      <FamilyFormDialog
        isOpen={true}
        onClose={vi.fn()}
        family={{
          id: 1,
          title: "Existing Family",
          description: "Test",
          member_count: 5,
          member_repository_ids: [],
          created_at: "2026-03-12T00:00:00Z",
          updated_at: "2026-03-12T00:00:00Z",
        }}
      />
    );

    expect(screen.getByText("Edit Family")).toBeInTheDocument();
  });
});

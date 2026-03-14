import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SynthesisHistoryPanel } from "@/components/ideas/SynthesisHistoryPanel";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockRuns = [
  {
    id: 1,
    idea_family_id: 1,
    run_type: "combiner",
    status: "completed",
    input_repository_ids: [10, 20],
    output_text: "Output 1",
    title: "Test Run 1",
    summary: "Summary 1",
    key_insights: ["Insight A", "Insight B"],
    error_message: null,
    started_at: "2026-03-10T10:00:00Z",
    completed_at: "2026-03-10T10:05:00Z",
    created_at: "2026-03-10T10:00:00Z",
  },
  {
    id: 2,
    idea_family_id: 1,
    run_type: "obsession",
    status: "failed",
    input_repository_ids: [30],
    output_text: null,
    title: "Test Run 2",
    summary: null,
    key_insights: null,
    error_message: "Error",
    started_at: "2026-03-11T10:00:00Z",
    completed_at: null,
    created_at: "2026-03-11T10:00:00Z",
  },
];

vi.mock("@/hooks/useSynthesis", () => ({
  useSynthesisRuns: (familyId: number, filters?: any) => {
    let filtered = [...mockRuns];

    if (filters?.status) {
      filtered = filtered.filter(r => r.status === filters.status);
    }

    if (filters?.search) {
      const query = filters.search.toLowerCase();
      filtered = filtered.filter(r =>
        r.title?.toLowerCase().includes(query) ||
        r.summary?.toLowerCase().includes(query) ||
        JSON.stringify(r.key_insights).toLowerCase().includes(query)
      );
    }

    if (filters?.repositoryId) {
      filtered = filtered.filter(r => r.input_repository_ids.includes(filters.repositoryId));
    }

    if (filters?.dateFrom) {
      filtered = filtered.filter(r => r.created_at >= filters.dateFrom);
    }

    if (filters?.dateTo) {
      filtered = filtered.filter(r => r.created_at <= filters.dateTo);
    }

    return { data: filtered, isLoading: false };
  },
  useSynthesisRun: (id: number) => ({ data: mockRuns.find(r => r.id === id), isLoading: false }),
}));

describe("SynthesisHistoryPanel", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  it("renders synthesis history with grouping", () => {
    render(<SynthesisHistoryPanel familyId={1} />, { wrapper });
    expect(screen.getByText("Synthesis History")).toBeInTheDocument();
    expect(screen.getByText("Combiner Runs")).toBeInTheDocument();
    expect(screen.getByText("obsession Runs")).toBeInTheDocument();
  });

  it("filters by status", async () => {
    render(<SynthesisHistoryPanel familyId={1} />, { wrapper });
    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "completed" } });
    await waitFor(() => {
      expect(screen.getByText("Test Run 1")).toBeInTheDocument();
      expect(screen.queryByText("Test Run 2")).not.toBeInTheDocument();
    });
  });

  it("searches across title and summary", async () => {
    render(<SynthesisHistoryPanel familyId={1} />, { wrapper });
    const searchInput = screen.getByPlaceholderText("Search title, summary, insights...");
    fireEvent.change(searchInput, { target: { value: "Summary 1" } });
    await waitFor(() => {
      expect(screen.getByText("Test Run 1")).toBeInTheDocument();
      expect(screen.queryByText("Test Run 2")).not.toBeInTheDocument();
    });
  });

  it("allows selecting runs for comparison", async () => {
    render(<SynthesisHistoryPanel familyId={1} />, { wrapper });
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);
    await waitFor(() => {
      expect(screen.getByText("2 selected for comparison")).toBeInTheDocument();
      expect(screen.getByText("Compare")).toBeEnabled();
    });
  });

  it("filters by repository ID", async () => {
    render(<SynthesisHistoryPanel familyId={1} />, { wrapper });
    const repoInput = screen.getByPlaceholderText(/repository id/i);
    fireEvent.change(repoInput, { target: { value: "30" } });
    await waitFor(() => {
      expect(screen.queryByText("Test Run 1")).not.toBeInTheDocument();
      expect(screen.getByText("Test Run 2")).toBeInTheDocument();
    });
  });

  it("searches in key insights", async () => {
    render(<SynthesisHistoryPanel familyId={1} />, { wrapper });
    const searchInput = screen.getByPlaceholderText("Search title, summary, insights...");
    fireEvent.change(searchInput, { target: { value: "Insight A" } });
    await waitFor(() => {
      expect(screen.getByText("Test Run 1")).toBeInTheDocument();
      expect(screen.queryByText("Test Run 2")).not.toBeInTheDocument();
    });
  });

  it("filters by date range", async () => {
    render(<SynthesisHistoryPanel familyId={1} />, { wrapper });
    const dateInputs = screen.getAllByPlaceholderText(/from|to/i);
    fireEvent.change(dateInputs[0], { target: { value: "2026-03-11" } });
    await waitFor(() => {
      expect(screen.queryByText("Test Run 1")).not.toBeInTheDocument();
      expect(screen.getByText("Test Run 2")).toBeInTheDocument();
    });
  });

  it("clears comparison state when family changes", async () => {
    const { rerender } = render(<SynthesisHistoryPanel familyId={1} />, { wrapper });
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    await waitFor(() => {
      expect(screen.getByText("1 selected for comparison")).toBeInTheDocument();
    });

    rerender(<SynthesisHistoryPanel familyId={2} />);
    await waitFor(() => {
      expect(screen.queryByText("selected for comparison")).not.toBeInTheDocument();
    });
  });
});

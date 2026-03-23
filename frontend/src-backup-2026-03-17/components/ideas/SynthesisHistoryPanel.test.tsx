import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SynthesisHistoryPanel } from "./SynthesisHistoryPanel";
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
    key_insights: { insights: ["Insight A", "Insight B"] },
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
  useSynthesisRuns: () => ({ data: mockRuns, isLoading: false }),
  useSynthesisRun: (id: number) => ({ data: mockRuns.find(r => r.id === id), isLoading: false }),
}));

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

describe("SynthesisHistoryPanel", () => {
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
});

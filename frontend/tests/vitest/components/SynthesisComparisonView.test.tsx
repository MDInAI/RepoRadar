import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SynthesisComparisonView } from "@/components/ideas/SynthesisComparisonView";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const useSynthesisRunCalls: Array<number | null | undefined> = [];

const mockRuns = [
  {
    id: 1,
    idea_family_id: 1,
    run_type: "combiner",
    status: "completed",
    input_repository_ids: [10, 20],
    output_text: "Output 1",
    title: "Run 1",
    summary: "Summary 1",
    key_insights: ["Insight A"],
    error_message: null,
    started_at: "2026-03-10T10:00:00Z",
    completed_at: "2026-03-10T10:05:00Z",
    created_at: "2026-03-10T10:00:00Z",
  },
  {
    id: 2,
    idea_family_id: 1,
    run_type: "combiner",
    status: "completed",
    input_repository_ids: [20, 30],
    output_text: "Output 2",
    title: "Run 2",
    summary: "Summary 2",
    key_insights: ["Insight B"],
    error_message: null,
    started_at: "2026-03-11T10:00:00Z",
    completed_at: "2026-03-11T10:05:00Z",
    created_at: "2026-03-11T10:00:00Z",
  },
  {
    id: 3,
    idea_family_id: 1,
    run_type: "combiner",
    status: "completed",
    input_repository_ids: [20, 30, 50],
    output_text: "Output 3",
    title: "Run 3",
    summary: "Summary 3",
    key_insights: [],
    error_message: null,
    started_at: "2026-03-12T10:00:00Z",
    completed_at: "2026-03-12T10:05:00Z",
    created_at: "2026-03-12T10:00:00Z",
  },
];

const threeRunMocks = [
  { ...mockRuns[0], input_repository_ids: [10, 20, 30] },
  { ...mockRuns[1], input_repository_ids: [20, 30, 40] },
  { ...mockRuns[2], input_repository_ids: [20, 30, 50] },
];

let mockIsLoading = false;
let mockDataSet: typeof mockRuns = mockRuns;

vi.mock("@/hooks/useSynthesis", () => ({
  useSynthesisRun: (id: number | null | undefined) => {
    useSynthesisRunCalls.push(id);
    return { data: mockDataSet.find(r => r.id === id), isLoading: mockIsLoading };
  },
}));

vi.mock("@/api/repositories", () => ({
  fetchRepositoryDetail: (id: number) => Promise.resolve({ github_repository_id: id, full_name: `repo-${id}` }),
}));

describe("SynthesisComparisonView", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    useSynthesisRunCalls.length = 0;
    mockIsLoading = false;
    mockDataSet = mockRuns;
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  it("renders comparison for multiple runs", () => {
    render(<SynthesisComparisonView runIds={[1, 2]} onClose={() => {}} />, { wrapper });
    expect(screen.getByText("Compare Synthesis Runs")).toBeInTheDocument();
    expect(screen.getByText("Run 1")).toBeInTheDocument();
    expect(screen.getByText("Run 2")).toBeInTheDocument();
  });

  it("shows repository differences", async () => {
    render(<SynthesisComparisonView runIds={[1, 2]} onClose={() => {}} />, { wrapper });

    await screen.findByText("Run 1");
    await screen.findByText("Run 2");

    const uniqueLabels = await screen.findAllByText(/Unique to this run:/i);
    expect(uniqueLabels.length).toBeGreaterThan(0);
  });

  it("passes null rather than undefined for an absent third run", () => {
    render(<SynthesisComparisonView runIds={[1, 2]} onClose={() => {}} />, { wrapper });
    expect(useSynthesisRunCalls).toEqual([1, 2, null]);
  });

  it("performs export comparison when button clicked", async () => {
    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: { writeText: writeTextSpy },
    });

    render(<SynthesisComparisonView runIds={[1, 2]} onClose={() => {}} />, { wrapper });

    await screen.findByText("Run 1");

    const exportButton = screen.getByText("Export Comparison");
    fireEvent.click(exportButton);

    await waitFor(() => {
      expect(writeTextSpy).toHaveBeenCalled();
      const capturedText = writeTextSpy.mock.calls[0][0];
      expect(capturedText).toContain("Run 1");
      expect(capturedText).toContain("Run 2");
    });
  });

  it("disables export button while runs are loading", () => {
    mockIsLoading = true;

    render(<SynthesisComparisonView runIds={[1, 2]} onClose={() => {}} />, { wrapper });

    const exportButton = screen.getByText("Export Comparison");
    expect(exportButton).toBeDisabled();
  });

  it("correctly identifies common repos across all runs", async () => {
    mockDataSet = threeRunMocks;

    render(<SynthesisComparisonView runIds={[1, 2, 3]} onClose={() => {}} />, { wrapper });

    await screen.findByText("Run 1");

    const commonLabels = await screen.findAllByText(/Common:/i);
    expect(commonLabels.length).toBe(3);
  });

  it("disables export button when run data fails to load", () => {
    mockDataSet = [];

    render(<SynthesisComparisonView runIds={[1, 2]} onClose={() => {}} />, { wrapper });

    const exportButton = screen.getByText("Export Comparison");
    expect(exportButton).toBeDisabled();
  });

  it("prevents export with partial data", async () => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    mockDataSet = [mockRuns[0]]; // Only first run loads

    render(<SynthesisComparisonView runIds={[1, 2]} onClose={() => {}} />, { wrapper });

    await screen.findByText("Run 1");

    const exportButton = screen.getByText("Export Comparison");
    expect(exportButton).toBeDisabled();

    alertSpy.mockRestore();
  });
});

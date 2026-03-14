import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { SynthesisRunDetailDialog } from "@/components/ideas/SynthesisRunDetailDialog";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockRun = {
  id: 1,
  idea_family_id: 1,
  run_type: "combiner",
  status: "completed",
  input_repository_ids: [10, 20],
  output_text: "Full output text",
  title: "Test Run",
  summary: "Test summary",
  key_insights: ["Insight 1", "Insight 2"],
  error_message: null,
  started_at: "2026-03-10T10:00:00Z",
  completed_at: "2026-03-10T10:05:00Z",
  created_at: "2026-03-10T10:00:00Z",
};

vi.mock("@/hooks/useSynthesis", () => ({
  useSynthesisRun: () => ({ data: mockRun, isLoading: false }),
}));

let resolveFamilyRequest: ((value: { id: number; title: string }) => void) | null = null;
let resolveRepositoryRequests: Array<(value: { github_repository_id: number; full_name: string }) => void> = [];

vi.mock("@/api/repositories", () => ({
  fetchRepositoryDetail: (id: number) =>
    new Promise<{ github_repository_id: number; full_name: string }>((resolve) => {
      resolveRepositoryRequests.push(resolve);
    }),
}));

vi.mock("@/api/idea-families", () => ({
  fetchIdeaFamily: () =>
    new Promise<{ id: number; title: string }>((resolve) => {
      resolveFamilyRequest = resolve;
    }),
}));

describe("SynthesisRunDetailDialog", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    resolveFamilyRequest = null;
    resolveRepositoryRequests = [];
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  it("renders run details", () => {
    render(<SynthesisRunDetailDialog runId={1} onClose={() => {}} />, { wrapper });
    expect(screen.getByText("Test Run")).toBeInTheDocument();
    expect(screen.getByText("Test summary")).toBeInTheDocument();
  });

  it("shows export buttons", () => {
    render(<SynthesisRunDetailDialog runId={1} onClose={() => {}} />, { wrapper });
    expect(screen.getByTitle("Export as Markdown")).toBeInTheDocument();
    expect(screen.getByTitle("Export as JSON")).toBeInTheDocument();
    expect(screen.getByTitle("Export as Text")).toBeInTheDocument();
  });

  it("disables export buttons until metadata loads", async () => {
    render(<SynthesisRunDetailDialog runId={1} onClose={() => {}} />, { wrapper });

    await waitFor(() => {
      const markdownButton = screen.getByTitle("Export as Markdown");
      const jsonButton = screen.getByTitle("Export as JSON");
      const textButton = screen.getByTitle("Export as Text");

      expect(markdownButton).toBeDisabled();
      expect(jsonButton).toBeDisabled();
      expect(textButton).toBeDisabled();
    });
  });

  it("performs markdown export with correct filename and content", async () => {
    const createObjectURLSpy = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

    render(<SynthesisRunDetailDialog runId={1} onClose={() => {}} />, { wrapper });

    await waitFor(() => {
      if (resolveFamilyRequest) resolveFamilyRequest({ id: 1, title: "Test Family" });
      resolveRepositoryRequests.forEach((resolve, index) => {
        const id = mockRun.input_repository_ids[index];
        resolve({ github_repository_id: id, full_name: `repo-${id}` });
      });
    });

    await waitFor(() => expect(screen.getByTitle("Export as Markdown")).toBeEnabled(), { timeout: 2000 });
    await new Promise(resolve => setTimeout(resolve, 100));

    fireEvent.click(screen.getByTitle("Export as Markdown"));

    await waitFor(() => expect(createObjectURLSpy).toHaveBeenCalled());

    const blob = createObjectURLSpy.mock.calls[0][0] as Blob;
    const text = await blob.text();

    expect(text).toContain("Test Run");
    expect(text).toContain("repo-10");
    expect(text).toContain("repo-20");
    expect(text).toContain("3/10/2026");

    vi.restoreAllMocks();
  });

  it("performs JSON export with correct filename and payload", async () => {
    const createObjectURLSpy = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

    render(<SynthesisRunDetailDialog runId={1} onClose={() => {}} />, { wrapper });

    await waitFor(() => {
      if (resolveFamilyRequest) resolveFamilyRequest({ id: 1, title: "Test Family" });
      resolveRepositoryRequests.forEach((resolve, index) => {
        const id = mockRun.input_repository_ids[index];
        resolve({ github_repository_id: id, full_name: `repo-${id}` });
      });
    });

    await waitFor(() => expect(screen.getByTitle("Export as JSON")).toBeEnabled(), { timeout: 2000 });
    await new Promise(resolve => setTimeout(resolve, 100));

    fireEvent.click(screen.getByTitle("Export as JSON"));

    await waitFor(() => expect(createObjectURLSpy).toHaveBeenCalled());

    const blob = createObjectURLSpy.mock.calls[0][0] as Blob;
    const text = await blob.text();
    const parsed = JSON.parse(text);

    expect(parsed.title).toBe("Test Run");
    expect(parsed.source_repositories).toContain("repo-10");
    expect(parsed.source_repositories).toContain("repo-20");
    expect(parsed.created_at).toContain("2026-03-10");

    vi.restoreAllMocks();
  });

  it("performs text export with correct filename and content", async () => {
    const createObjectURLSpy = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

    render(<SynthesisRunDetailDialog runId={1} onClose={() => {}} />, { wrapper });

    await waitFor(() => {
      if (resolveFamilyRequest) resolveFamilyRequest({ id: 1, title: "Test Family" });
      resolveRepositoryRequests.forEach((resolve, index) => {
        const id = mockRun.input_repository_ids[index];
        resolve({ github_repository_id: id, full_name: `repo-${id}` });
      });
    });

    await waitFor(() => expect(screen.getByTitle("Export as Text")).toBeEnabled(), { timeout: 2000 });
    await new Promise(resolve => setTimeout(resolve, 100));

    fireEvent.click(screen.getByTitle("Export as Text"));

    await waitFor(() => expect(createObjectURLSpy).toHaveBeenCalled());

    const blob = createObjectURLSpy.mock.calls[0][0] as Blob;
    const text = await blob.text();

    expect(text).toContain("Test Run");
    expect(text).toContain("repo-10, repo-20");
    expect(text).toContain("2026");

    vi.restoreAllMocks();
  });
});

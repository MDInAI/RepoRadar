import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ObsessionContextPanel } from './ObsessionContextPanel';
import { obsessionApi } from '@/lib/api/obsession';
import { vi } from 'vitest';

vi.mock('@/lib/api/obsession');

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('ObsessionContextPanel', () => {
  it('renders loading state', () => {
    vi.mocked(obsessionApi.listContexts).mockReturnValue(new Promise(() => {}));
    render(<ObsessionContextPanel ideaFamilyId={1} />, { wrapper: createWrapper() });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('renders empty state when no contexts', async () => {
    vi.mocked(obsessionApi.listContexts).mockResolvedValue([]);
    render(<ObsessionContextPanel ideaFamilyId={1} />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText(/no obsession agents/i)).toBeInTheDocument();
    });
  });

  it('renders context list', async () => {
    vi.mocked(obsessionApi.listContexts).mockResolvedValue([
      {
        id: 1,
        idea_family_id: 1,
        synthesis_run_id: null,
        idea_search_id: null,
        idea_text: null,
        title: 'Test Context',
        description: 'Test description',
        status: 'active',
        refresh_policy: 'manual',
        last_refresh_at: null,
        synthesis_run_count: 3,
        created_at: '2026-03-13T00:00:00Z',
        updated_at: '2026-03-13T00:00:00Z',
      },
    ]);

    render(<ObsessionContextPanel ideaFamilyId={1} />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Test Context')).toBeInTheDocument();
      expect(screen.getByText('Test description')).toBeInTheDocument();
      expect(screen.getByText(/Runs: 3/)).toBeInTheDocument();
    });
  });
});

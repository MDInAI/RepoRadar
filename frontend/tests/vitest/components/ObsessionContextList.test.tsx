import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ObsessionContextList } from '@/components/ideas/ObsessionContextList';
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/hooks/useObsession', () => ({
  useObsessionContexts: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => ({ get: vi.fn(), toString: () => '' }),
}));

const { useObsessionContexts } = await import('@/hooks/useObsession');

describe('ObsessionContextList', () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  it('renders loading state', () => {
    vi.mocked(useObsessionContexts).mockReturnValue({
      data: undefined,
      isLoading: true,
    } as any);

    render(<ObsessionContextList />, { wrapper });
    expect(screen.getByText('Loading contexts...')).toBeInTheDocument();
  });

  it('renders empty state', () => {
    vi.mocked(useObsessionContexts).mockReturnValue({
      data: [],
      isLoading: false,
    } as any);

    render(<ObsessionContextList />, { wrapper });
    expect(screen.getByText('No Obsession contexts found')).toBeInTheDocument();
  });

  it('renders context list', async () => {
    const contexts = [
      {
        id: 1,
        title: 'Test Context',
        status: 'active',
        synthesis_run_count: 5,
        refresh_policy: 'manual',
        created_at: '2024-01-01T00:00:00Z',
      },
    ];

    vi.mocked(useObsessionContexts).mockReturnValue({
      data: contexts,
      isLoading: false,
    } as any);

    render(<ObsessionContextList />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText('Test Context')).toBeInTheDocument();
      expect(screen.getByText('5 runs')).toBeInTheDocument();
      expect(screen.getByText('active')).toBeInTheDocument();
    });
  });

  it('filters contexts by status', async () => {
    const contexts = [
      { id: 1, title: 'Active', status: 'active', synthesis_run_count: 5, refresh_policy: 'manual', created_at: '2024-01-01T00:00:00Z' },
      { id: 2, title: 'Paused', status: 'paused', synthesis_run_count: 3, refresh_policy: 'manual', created_at: '2024-01-02T00:00:00Z' },
    ];

    vi.mocked(useObsessionContexts).mockReturnValue({ data: contexts, isLoading: false } as any);

    render(<ObsessionContextList />, { wrapper });

    const statusSelect = screen.getByDisplayValue('All Status');
    fireEvent.change(statusSelect, { target: { value: 'active' } });

    await waitFor(() => {
      expect(useObsessionContexts).toHaveBeenCalledWith(undefined, 'active');
    });
  });

  it('sorts contexts by newest first', async () => {
    const contexts = [
      { id: 1, title: 'Old', status: 'active', synthesis_run_count: 5, refresh_policy: 'manual', created_at: '2024-01-01T00:00:00Z' },
      { id: 2, title: 'New', status: 'active', synthesis_run_count: 3, refresh_policy: 'manual', created_at: '2024-01-02T00:00:00Z' },
    ];

    vi.mocked(useObsessionContexts).mockReturnValue({ data: contexts, isLoading: false } as any);

    render(<ObsessionContextList />, { wrapper });

    const items = screen.getAllByText(/Old|New/);
    expect(items[0]).toHaveTextContent('New');
    expect(items[1]).toHaveTextContent('Old');
  });

  it('hides completed contexts when showCompleted is false', () => {
    const contexts = [
      { id: 1, title: 'Active Context', status: 'active', synthesis_run_count: 5, refresh_policy: 'manual', created_at: '2024-01-01T00:00:00Z' },
      { id: 2, title: 'Completed Context', status: 'completed', synthesis_run_count: 3, refresh_policy: 'manual', created_at: '2024-01-02T00:00:00Z' },
    ];

    vi.mocked(useObsessionContexts).mockReturnValue({ data: contexts, isLoading: false } as any);

    render(<ObsessionContextList showCompleted={false} />, { wrapper });

    expect(screen.getByText('Active Context')).toBeInTheDocument();
    expect(screen.queryByText('Completed Context')).not.toBeInTheDocument();
  });
});

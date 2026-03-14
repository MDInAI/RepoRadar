import { render, screen } from '@testing-library/react';
import { SynthesisRunTimeline } from '@/components/ideas/SynthesisRunTimeline';
import { describe, it, expect, vi } from 'vitest';

describe('SynthesisRunTimeline', () => {
  const mockOnViewOutput = vi.fn();

  it('renders empty state', () => {
    render(<SynthesisRunTimeline runs={[]} onViewOutput={mockOnViewOutput} />);
    expect(screen.getByText('No synthesis runs yet')).toBeInTheDocument();
  });

  it('renders run timeline with success rate', () => {
    const runs = [
      {
        id: 1,
        run_type: 'obsession',
        status: 'completed',
        title: 'Run 1',
        started_at: '2024-01-01T00:00:00Z',
        completed_at: '2024-01-01T00:01:00Z',
        created_at: '2024-01-01T00:00:00Z',
      },
      {
        id: 2,
        run_type: 'obsession',
        status: 'failed',
        title: 'Run 2',
        started_at: null,
        completed_at: null,
        created_at: '2024-01-02T00:00:00Z',
      },
    ];

    render(<SynthesisRunTimeline runs={runs} onViewOutput={mockOnViewOutput} />);

    expect(screen.getByText('Total Runs: 2')).toBeInTheDocument();
    expect(screen.getByText('Success Rate: 50%')).toBeInTheDocument();
    expect(screen.getByText('Run 1')).toBeInTheDocument();
    expect(screen.getByText('Run 2')).toBeInTheDocument();
  });
});

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemorySegmentViewer } from './MemorySegmentViewer';
import type { MemorySegmentResponse } from '@/lib/api/memory';

describe('MemorySegmentViewer', () => {
  const mockSegment: MemorySegmentResponse = {
    id: 1,
    segment_key: 'insights',
    content: 'Test content',
    content_type: 'markdown',
    created_at: '2026-03-14T00:00:00Z',
    updated_at: '2026-03-14T00:00:00Z',
  };

  it('renders segment key and content type', () => {
    render(<MemorySegmentViewer segment={mockSegment} onClose={vi.fn()} />);
    expect(screen.getByText('insights')).toBeInTheDocument();
    expect(screen.getByText('markdown')).toBeInTheDocument();
  });

  it('renders markdown content', () => {
    render(<MemorySegmentViewer segment={mockSegment} onClose={vi.fn()} />);
    expect(screen.getByText('Test content')).toBeInTheDocument();
  });

  it('renders JSON content formatted', () => {
    const jsonSegment = {
      ...mockSegment,
      content: '["insight1","insight2"]',
      content_type: 'json',
    };
    render(<MemorySegmentViewer segment={jsonSegment} onClose={vi.fn()} />);
    expect(screen.getByText(/"insight1"/)).toBeInTheDocument();
  });
});

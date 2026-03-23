'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useObsessionContexts } from '@/hooks/useObsession';
import { formatAppDateTime } from '@/lib/time';
import { ObsessionContextDetailDialog } from './ObsessionContextDetailDialog';

interface ObsessionContextListProps {
  ideaFamilyId?: number;
  showCompleted?: boolean;
}

export function ObsessionContextList({ ideaFamilyId, showCompleted = true }: ObsessionContextListProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [statusFilter, setStatusFilter] = useState<string>(searchParams.get('status') || 'all');
  const [sortOrder, setSortOrder] = useState<'newest' | 'oldest' | 'recently-refreshed'>((searchParams.get('sort') as any) || 'newest');
  const [selectedContextId, setSelectedContextId] = useState<number | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());
    if (statusFilter !== 'all') {
      params.set('status', statusFilter);
    } else {
      params.delete('status');
    }
    params.set('sort', sortOrder);
    router.replace(`?${params.toString()}`, { scroll: false });
  }, [statusFilter, sortOrder]);

  const { data: contexts, isLoading } = useObsessionContexts(ideaFamilyId, statusFilter === 'all' ? undefined : statusFilter);

  const filteredContexts = contexts ? contexts.filter(c => showCompleted || c.status !== 'completed') : [];

  const sortedContexts = filteredContexts ? [...filteredContexts].sort((a, b) => {
    if (sortOrder === 'recently-refreshed') {
      const dateA = a.last_refresh_at ? new Date(a.last_refresh_at).getTime() : 0;
      const dateB = b.last_refresh_at ? new Date(b.last_refresh_at).getTime() : 0;
      return dateB - dateA;
    }
    const dateA = new Date(a.created_at).getTime();
    const dateB = new Date(b.created_at).getTime();
    return sortOrder === 'newest' ? dateB - dateA : dateA - dateB;
  }) : [];

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-100 text-green-800';
      case 'paused': return 'bg-yellow-100 text-yellow-800';
      case 'completed': return 'bg-gray-100 text-gray-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  if (isLoading) return <div className="text-sm text-gray-500">Loading contexts...</div>;

  return (
    <div className="space-y-3">
      <div className="flex gap-2 items-center">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="text-sm border rounded px-2 py-1"
        >
          <option value="all">All Status</option>
          <option value="active">Active</option>
          <option value="paused">Paused</option>
          <option value="completed">Completed</option>
        </select>
        <select
          value={sortOrder}
          onChange={(e) => setSortOrder(e.target.value as 'newest' | 'oldest' | 'recently-refreshed')}
          className="text-sm border rounded px-2 py-1"
        >
          <option value="newest">Newest First</option>
          <option value="oldest">Oldest First</option>
          <option value="recently-refreshed">Recently Refreshed</option>
        </select>
      </div>

      {sortedContexts.length === 0 ? (
        <div className="text-sm text-gray-500">No Obsession contexts found</div>
      ) : (
        <div className="space-y-2">
          {sortedContexts.map((context) => (
            <div key={context.id} className="border rounded p-3 hover:bg-gray-50">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="font-medium text-sm">{context.title}</div>
                  <div className="flex gap-2 items-center mt-1">
                    <span className={`text-xs px-2 py-0.5 rounded ${getStatusColor(context.status)}`}>
                      {context.status}
                    </span>
                    <span className="text-xs text-gray-500">
                      {context.synthesis_run_count} runs
                    </span>
                    <span className="text-xs text-gray-500">
                      {context.refresh_policy}
                    </span>
                  </div>
                  {context.last_refresh_at && (
                    <div className="text-xs text-gray-500 mt-1">
                      Last refresh: {formatAppDateTime(context.last_refresh_at)}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => setSelectedContextId(context.id)}
                  className="text-sm text-blue-600 hover:text-blue-800"
                >
                  View Details
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {selectedContextId && (
        <ObsessionContextDetailDialog
          contextId={selectedContextId}
          onClose={() => setSelectedContextId(null)}
        />
      )}
    </div>
  );
}

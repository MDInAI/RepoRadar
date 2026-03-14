'use client';

import { useState, useEffect } from 'react';
import { useObsessionContexts } from '@/hooks/useObsession';
import { ObsessionContextDetailDialog } from './ObsessionContextDetailDialog';

interface ObsessionContextPanelProps {
  ideaFamilyId: number;
}

export function ObsessionContextPanel({ ideaFamilyId }: ObsessionContextPanelProps) {
  const { data: contexts, isLoading } = useObsessionContexts(ideaFamilyId, 'active');
  const [selectedContextId, setSelectedContextId] = useState<number | null>(null);

  useEffect(() => {
    const handleViewContext = (event: CustomEvent) => {
      setSelectedContextId(event.detail.contextId);
    };

    window.addEventListener('view-obsession-context', handleViewContext as EventListener);
    return () => window.removeEventListener('view-obsession-context', handleViewContext as EventListener);
  }, []);

  if (isLoading) {
    return <div className="text-sm text-gray-500">Loading obsession contexts...</div>;
  }

  if (!contexts || contexts.length === 0) {
    return <div className="text-sm text-gray-500">No obsession agents running</div>;
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">Active Obsession Agents</h3>
      <div className="space-y-2">
        {contexts.map((context) => (
          <div
            key={context.id}
            className="border rounded p-3 hover:bg-gray-50 cursor-pointer"
            onClick={() => setSelectedContextId(context.id)}
          >
            <div className="flex justify-between items-start">
              <div className="flex-1">
                <div className="font-medium">{context.title}</div>
                {context.description && (
                  <div className="text-sm text-gray-600 mt-1">{context.description}</div>
                )}
                <div className="text-xs text-gray-500 mt-2 space-x-3">
                  <span>Status: {context.status}</span>
                  <span>Policy: {context.refresh_policy}</span>
                  <span>Runs: {context.synthesis_run_count}</span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {selectedContextId && (
        <ObsessionContextDetailDialog
          contextId={selectedContextId}
          onClose={() => setSelectedContextId(null)}
        />
      )}
    </div>
  );
}

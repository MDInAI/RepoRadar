'use client';

import { useState } from 'react';
import { useObsessionContext, useUpdateObsessionContext, useTriggerRefresh } from '@/hooks/useObsession';
import { useMemorySegments } from '@/hooks/useMemory';
import { formatAppDateTime } from '@/lib/time';
import { ObsessionContextFormDialog } from './ObsessionContextFormDialog';
import { MemorySegmentViewer } from './MemorySegmentViewer';
import { SynthesisRunTimeline } from './SynthesisRunTimeline';
import { SynthesisRunDetailDialog } from './SynthesisRunDetailDialog';
import { ObsessionScopePanel } from './ObsessionScopePanel';
import { ObsessionStateSummary } from './ObsessionStateSummary';
import { IdeaSearchProgressBar } from '@/components/scout/IdeaSearchProgressBar';
import { useIdeaSearch } from '@/hooks/useIdeaScout';
import type { MemorySegmentResponse } from '@/lib/api/memory';

interface ObsessionContextDetailDialogProps {
  contextId: number;
  onClose: () => void;
}

export function ObsessionContextDetailDialog({ contextId, onClose }: ObsessionContextDetailDialogProps) {
  const { data: context, isLoading } = useObsessionContext(contextId);
  const { data: linkedSearch } = useIdeaSearch(context?.idea_search_id ?? 0);
  const { data: memorySegments } = useMemorySegments(contextId);
  const updateMutation = useUpdateObsessionContext();
  const refreshMutation = useTriggerRefresh();
  const [isEditing, setIsEditing] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'runs' | 'memory'>('overview');
  const [selectedSegment, setSelectedSegment] = useState<MemorySegmentResponse | null>(null);
  const [viewingRunId, setViewingRunId] = useState<number | null>(null);

  const handleTriggerRefresh = async () => {
    await refreshMutation.mutateAsync(contextId);
  };

  const handleToggleStatus = async () => {
    if (!context) return;
    const newStatus = context.status === 'active' ? 'paused' : 'active';
    await updateMutation.mutateAsync({
      contextId,
      data: { status: newStatus },
    });
  };

  if (isLoading || !context) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-white rounded-lg p-6 max-w-2xl w-full">
          <div>Loading...</div>
        </div>
      </div>
    );
  }

  if (isEditing) {
    return (
      <ObsessionContextFormDialog
        onClose={() => setIsEditing(false)}
        ideaFamilyId={context.idea_family_id}
        existingContext={context}
      />
    );
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg p-6 max-w-2xl w-full max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-start mb-4">
          <h2 className="text-xl font-semibold">{context.title}</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            ✕
          </button>
        </div>

        <div className="flex gap-4 mb-4 border-b">
          <button
            onClick={() => setActiveTab('overview')}
            className={`pb-2 px-1 ${activeTab === 'overview' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-600'}`}
          >
            Overview
          </button>
          <button
            onClick={() => setActiveTab('runs')}
            className={`pb-2 px-1 ${activeTab === 'runs' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-600'}`}
          >
            Synthesis Runs ({context.synthesis_runs.length})
          </button>
          <button
            onClick={() => setActiveTab('memory')}
            className={`pb-2 px-1 ${activeTab === 'memory' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-600'}`}
          >
            Memory {memorySegments && memorySegments.length > 0 && `(${memorySegments.length})`}
          </button>
        </div>

        {activeTab === 'overview' && (
          <div className="space-y-4">
            <ObsessionStateSummary
              totalRuns={context.synthesis_runs.length}
              successfulRuns={context.synthesis_runs.filter(r => r.status === 'completed').length}
              failedRuns={context.synthesis_runs.filter(r => r.status === 'failed').length}
              memorySegments={memorySegments?.length || 0}
              status={context.status}
              refreshPolicy={context.refresh_policy}
              onTriggerRefresh={handleTriggerRefresh}
              onToggleStatus={handleToggleStatus}
              onEdit={() => setIsEditing(true)}
              isRefreshing={refreshMutation.isPending}
              isUpdating={updateMutation.isPending}
            />

            <div>
              <div className="text-sm font-medium text-gray-700 mb-2">Description</div>
              <div className="text-sm text-gray-600">{context.description || 'No description'}</div>
            </div>

            {linkedSearch && (
              <div>
                <div className="text-sm font-medium text-gray-700 mb-2">
                  Linked Idea Search — &ldquo;{linkedSearch.idea_text}&rdquo;
                </div>
                <IdeaSearchProgressBar
                  progress={linkedSearch.progress}
                  direction={linkedSearch.direction}
                />
                <div className="text-xs text-gray-500 mt-1">
                  {linkedSearch.total_repos_found} repos discovered &middot; Status: {linkedSearch.status}
                </div>
              </div>
            )}

            <ObsessionScopePanel
              familyTitle={context.family_title}
              repositories={context.repositories}
              ideaFamilyId={context.idea_family_id}
              scopeUpdatedAt={context.scope_updated_at}
              onViewFamily={context.idea_family_id ? () => window.location.href = `/ideas?family=${context.idea_family_id}` : undefined}
            />

            <div className="text-xs text-gray-500">
              Created: {formatAppDateTime(context.created_at)}
              {context.last_refresh_at && ` • Last refresh: ${formatAppDateTime(context.last_refresh_at)}`}
            </div>
          </div>
        )}

        {activeTab === 'runs' && (
          <SynthesisRunTimeline
            runs={context.synthesis_runs}
            onViewOutput={(runId) => setViewingRunId(runId)}
          />
        )}

        {activeTab === 'memory' && (
          <div className="space-y-4">
            {!memorySegments || memorySegments.length === 0 ? (
              <div className="text-sm text-gray-500">No memory segments stored yet</div>
            ) : (
              <div className="space-y-2">
                {memorySegments.map((segment) => (
                  <div key={segment.id} className="border rounded p-3 hover:bg-gray-50">
                    <div className="flex justify-between items-start">
                      <div className="flex-1">
                        <div className="font-medium text-sm">{segment.segment_key}</div>
                        <div className="text-xs text-gray-500">
                          <span className="bg-gray-200 px-2 py-0.5 rounded mr-2">{segment.content_type}</span>
                          Updated: {formatAppDateTime(segment.updated_at)}
                        </div>
                      </div>
                      <button
                        onClick={() => setSelectedSegment(segment)}
                        className="text-sm text-blue-600 hover:text-blue-800"
                      >
                        View
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {selectedSegment && (
        <MemorySegmentViewer
          segment={selectedSegment}
          onClose={() => setSelectedSegment(null)}
        />
      )}

      {viewingRunId && (
        <SynthesisRunDetailDialog
          runId={viewingRunId}
          onClose={() => setViewingRunId(null)}
        />
      )}
    </div>
  );
}

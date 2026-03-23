'use client';

import { useState } from 'react';
import { useCreateObsessionContext, useUpdateObsessionContext } from '@/hooks/useObsession';

interface ObsessionContextFormDialogProps {
  ideaFamilyId: number | null;
  onClose: () => void;
  onSuccess?: (contextId: number) => void;
  existingContext?: {
    id: number;
    title: string;
    description: string | null;
    refresh_policy: string;
  };
}

export function ObsessionContextFormDialog({ ideaFamilyId, onClose, onSuccess, existingContext }: ObsessionContextFormDialogProps) {
  const [title, setTitle] = useState(existingContext?.title || '');
  const [description, setDescription] = useState(existingContext?.description || '');
  const [refreshPolicy, setRefreshPolicy] = useState(existingContext?.refresh_policy || 'manual');
  const createMutation = useCreateObsessionContext();
  const updateMutation = useUpdateObsessionContext();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    if (existingContext) {
      await updateMutation.mutateAsync({
        contextId: existingContext.id,
        data: {
          title: title.trim(),
          description: description.trim() || null,
          refresh_policy: refreshPolicy,
        },
      });
      onSuccess?.(existingContext.id);
    } else {
      const result = await createMutation.mutateAsync({
        idea_family_id: ideaFamilyId!,
        title: title.trim(),
        description: description.trim() || null,
        refresh_policy: refreshPolicy,
      });
      onSuccess?.(result.id);
    }
    onClose();
  };

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg p-6 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-xl font-semibold mb-4">{existingContext ? 'Edit Obsession Agent' : 'Create Obsession Agent'}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Title *</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              required
              className="w-full border rounded px-3 py-2"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full border rounded px-3 py-2"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Refresh Policy</label>
            <select
              value={refreshPolicy}
              onChange={(e) => setRefreshPolicy(e.target.value)}
              className="w-full border rounded px-3 py-2"
            >
              <option value="manual">Manual</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
            </select>
          </div>

          <div className="flex gap-2 pt-4">
            <button
              type="submit"
              disabled={isPending || !title.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {isPending ? (existingContext ? 'Updating...' : 'Creating...') : (existingContext ? 'Update' : 'Create')}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border rounded hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

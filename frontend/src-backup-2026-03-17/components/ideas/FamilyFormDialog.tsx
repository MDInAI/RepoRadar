"use client";

import { useCreateIdeaFamily, useUpdateIdeaFamily } from "@/hooks/useIdeaFamilies";
import { useState, useEffect } from "react";
import type { IdeaFamily } from "@/api/idea-families";

interface FamilyFormDialogProps {
  isOpen: boolean;
  onClose: () => void;
  family?: IdeaFamily | null;
  onSubmit?: (title: string, description: string | null) => Promise<void>;
}

export function FamilyFormDialog({ isOpen, onClose, family, onSubmit }: FamilyFormDialogProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const createMutation = useCreateIdeaFamily();
  const updateMutation = useUpdateIdeaFamily();

  useEffect(() => {
    if (family) {
      setTitle(family.title);
      setDescription(family.description || "");
    } else {
      setTitle("");
      setDescription("");
    }
    setError(null);
  }, [family, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedTitle = title.trim();
    if (!trimmedTitle) return;

    setError(null);
    try {
      if (onSubmit) {
        await onSubmit(trimmedTitle, description || null);
      } else if (family) {
        await updateMutation.mutateAsync({
          familyId: family.id,
          data: { title: trimmedTitle, description: description || null },
        });
        onClose();
      } else {
        await createMutation.mutateAsync({
          title: trimmedTitle,
          description: description || null,
        });
        onClose();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save family");
    }
  };

  const isLoading = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-6 w-full max-w-md">
        <h2 className="text-xl font-bold mb-4">
          {family ? "Edit Family" : "Create Family"}
        </h2>
        {error && (
          <div className="bg-red-600/20 border border-red-600/50 text-red-400 px-4 py-2 rounded-lg text-sm">
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="title" className="block text-sm font-medium mb-1">
              Title <span className="text-red-400">*</span>
            </label>
            <input
              id="title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              required
              className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label htmlFor="description" className="block text-sm font-medium mb-1">
              Description
            </label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 rounded-lg text-sm transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading || !title.trim()}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg text-sm transition-colors disabled:opacity-50"
            >
              {isLoading ? "Saving..." : family ? "Update" : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

"use client";

import { useAddRepositoryToFamily } from "@/hooks/useIdeaFamilies";
import { useQuery } from "@tanstack/react-query";
import { fetchRepositoryCatalog } from "@/api/repositories";
import { useState, useMemo } from "react";

interface RepositorySelectorDialogProps {
  isOpen: boolean;
  onClose: () => void;
  familyId: number;
  existingRepoIds: number[];
}

export function RepositorySelectorDialog({
  isOpen,
  onClose,
  familyId,
  existingRepoIds,
}: RepositorySelectorDialogProps) {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [page, setPage] = useState(1);
  const addRepoMutation = useAddRepositoryToFamily();

  const { data: reposData, isLoading } = useQuery({
    queryKey: ["repositories", "catalog", "starred", page],
    queryFn: () => fetchRepositoryCatalog({
      page,
      pageSize: 100,
      sort: "stars",
      order: "desc",
      search: null,
      source: null,
      queueStatus: null,
      triageStatus: null,
      analysisStatus: null,
      hasFailures: false,
      monetization: null,
      minStars: null,
      maxStars: null,
      starredOnly: true,
      ideaFamilyId: null,
    }),
    enabled: isOpen,
  });

  if (!isOpen) return null;

  const availableRepos = reposData?.items.filter(
    (repo) => !existingRepoIds.includes(repo.github_repository_id)
  ) || [];

  const hasMorePages = reposData && page < reposData.total_pages;
  const showPagination = reposData && reposData.total_pages > 1;

  const handleToggle = (repoId: number) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(repoId)) {
      newSelected.delete(repoId);
    } else {
      newSelected.add(repoId);
    }
    setSelectedIds(newSelected);
  };

  const handleAdd = async () => {
    for (const repoId of selectedIds) {
      await addRepoMutation.mutateAsync({ familyId, repoId });
    }
    setSelectedIds(new Set());
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-6 w-full max-w-2xl max-h-[80vh] flex flex-col">
        <h2 className="text-xl font-bold mb-4">Add Repositories</h2>

        {isLoading ? (
          <p className="text-sm text-neutral-400">Loading repositories...</p>
        ) : availableRepos.length === 0 && !hasMorePages ? (
          <p className="text-sm text-neutral-400">No starred repositories available to add</p>
        ) : availableRepos.length === 0 && hasMorePages ? (
          <div className="text-sm text-neutral-400">
            <p>All repositories on this page are already in the family.</p>
            <p className="mt-2">Try the next page to see more repositories.</p>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto space-y-2 mb-4">
            {availableRepos.map((repo) => (
              <label
                key={repo.github_repository_id}
                className="flex items-start gap-3 p-3 border border-neutral-800 rounded-lg hover:bg-neutral-800/50 cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selectedIds.has(repo.github_repository_id)}
                  onChange={() => handleToggle(repo.github_repository_id)}
                  className="mt-1"
                />
                <div className="flex-1">
                  <h3 className="font-medium text-sm">{repo.full_name}</h3>
                  {repo.repository_description && (
                    <p className="text-xs text-neutral-400 mt-1">{repo.repository_description}</p>
                  )}
                </div>
              </label>
            ))}
          </div>
        )}

        {!isLoading && showPagination && (
          <div className="flex items-center justify-center gap-2 py-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 bg-neutral-800 hover:bg-neutral-700 rounded text-sm disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-sm text-neutral-400">
              Page {page} of {reposData?.total_pages}
            </span>
            <button
              onClick={() => setPage(p => Math.min(reposData?.total_pages || 1, p + 1))}
              disabled={!hasMorePages}
              className="px-3 py-1 bg-neutral-800 hover:bg-neutral-700 rounded text-sm disabled:opacity-50"
            >
              Next
            </button>
          </div>
        )}

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            disabled={addRepoMutation.isPending}
            className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 rounded-lg text-sm transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleAdd}
            disabled={selectedIds.size === 0 || addRepoMutation.isPending}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg text-sm transition-colors disabled:opacity-50"
          >
            {addRepoMutation.isPending ? "Adding..." : `Add Selected (${selectedIds.size})`}
          </button>
        </div>
      </div>
    </div>
  );
}

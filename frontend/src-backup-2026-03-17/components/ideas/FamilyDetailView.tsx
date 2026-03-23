"use client";

import { useIdeaFamily, useRemoveRepositoryFromFamily } from "@/hooks/useIdeaFamilies";
import { useQuery } from "@tanstack/react-query";
import { fetchRepositoryCatalog } from "@/api/repositories";
import { useState } from "react";

interface FamilyDetailViewProps {
  familyId: number;
  onEditFamily: () => void;
  onDeleteFamily: () => void;
  onAddRepositories: () => void;
}

export function FamilyDetailView({
  familyId,
  onEditFamily,
  onDeleteFamily,
  onAddRepositories,
}: FamilyDetailViewProps) {
  const [page, setPage] = useState(1);
  const { data: family, isLoading, error } = useIdeaFamily(familyId);
  const removeRepoMutation = useRemoveRepositoryFromFamily();

  const { data: reposData } = useQuery({
    queryKey: ["repositories", "catalog", "family", familyId, page],
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
      category: null,
      agentTag: null,
      userTag: null,
      monetization: null,
      minStars: null,
      maxStars: null,
      starredOnly: false,
      ideaFamilyId: familyId,
    }),
    enabled: !!family && family.member_count > 0,
  });

  if (isLoading) {
    return (
      <div className="flex-1 p-6">
        <p className="text-sm text-neutral-400">Loading family details...</p>
      </div>
    );
  }

  if (error || !family) {
    return (
      <div className="flex-1 p-6">
        <p className="text-sm text-red-400">Failed to load family details</p>
      </div>
    );
  }

  const repos = reposData?.items || [];
  const totalPages = reposData ? Math.ceil(reposData.total / 100) : 1;

  return (
    <div className="flex-1 p-6 flex flex-col gap-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{family.title}</h1>
          {family.description && (
            <p className="text-neutral-400 mt-2">{family.description}</p>
          )}
          <p className="text-sm text-neutral-500 mt-2">
            Created {new Date(family.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onEditFamily}
            className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 text-white rounded-lg text-sm transition-colors"
          >
            Edit
          </button>
          <button
            onClick={onDeleteFamily}
            className="px-4 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg text-sm transition-colors"
          >
            Delete
          </button>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">
            Repositories ({family.member_count})
          </h2>
          <button
            onClick={onAddRepositories}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm transition-colors"
          >
            + Add Repositories
          </button>
        </div>

        {repos.length === 0 ? (
          <div className="border border-neutral-800 rounded-lg p-8 text-center">
            <p className="text-neutral-400">No repositories in this family yet</p>
            <p className="text-sm text-neutral-500 mt-1">Add repositories to get started</p>
          </div>
        ) : (
          <div className="space-y-2">
            {repos.map((repo) => (
              <div
                key={repo.github_repository_id}
                className="border border-neutral-800 rounded-lg p-4 flex items-start justify-between"
              >
                <div className="flex-1">
                  <h3 className="font-medium">{repo.full_name}</h3>
                  {repo.repository_description && (
                    <p className="text-sm text-neutral-400 mt-1">
                      {repo.repository_description}
                    </p>
                  )}
                  <div className="flex gap-4 mt-2 text-xs text-neutral-500">
                    <span>⭐ {repo.stargazers_count}</span>
                    <span>🍴 {repo.forks_count}</span>
                  </div>
                </div>
                <button
                  onClick={() =>
                    removeRepoMutation.mutate({
                      familyId,
                      repoId: repo.github_repository_id,
                    })
                  }
                  disabled={removeRepoMutation.isPending}
                  className="px-3 py-1 text-sm text-red-400 hover:bg-red-600/20 rounded transition-colors disabled:opacity-50"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}

        {repos.length > 0 && totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 mt-4">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 bg-neutral-800 hover:bg-neutral-700 rounded text-sm disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-sm text-neutral-400">
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-3 py-1 bg-neutral-800 hover:bg-neutral-700 rounded text-sm disabled:opacity-50"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

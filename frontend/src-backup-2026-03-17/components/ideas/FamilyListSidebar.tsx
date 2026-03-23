"use client";

import { useIdeaFamilies } from "@/hooks/useIdeaFamilies";

interface FamilyListSidebarProps {
  selectedFamilyId: number | null;
  onSelectFamily: (familyId: number) => void;
  onCreateFamily: () => void;
}

export function FamilyListSidebar({
  selectedFamilyId,
  onSelectFamily,
  onCreateFamily,
}: FamilyListSidebarProps) {
  const { data: families, isLoading, error } = useIdeaFamilies();

  if (isLoading) {
    return (
      <aside className="w-80 border-r border-neutral-800 bg-neutral-900/50 p-4">
        <p className="text-sm text-neutral-400">Loading families...</p>
      </aside>
    );
  }

  if (error) {
    return (
      <aside className="w-80 border-r border-neutral-800 bg-neutral-900/50 p-4">
        <p className="text-sm text-red-400">Failed to load families</p>
      </aside>
    );
  }

  return (
    <aside className="w-80 border-r border-neutral-800 bg-neutral-900/50 p-4 flex flex-col gap-4">
      <button
        onClick={onCreateFamily}
        className="w-full px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium transition-colors"
      >
        + Create Family
      </button>

      {!families || families.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-sm text-neutral-400">No families yet</p>
            <p className="text-xs text-neutral-500 mt-1">Create one to get started</p>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {families.map((family) => (
            <button
              key={family.id}
              onClick={() => onSelectFamily(family.id)}
              className={`p-3 rounded-lg text-left transition-colors ${
                selectedFamilyId === family.id
                  ? "bg-indigo-600/20 border border-indigo-500/50"
                  : "bg-neutral-800/50 border border-neutral-700 hover:bg-neutral-800"
              }`}
            >
              <h3 className="font-medium text-sm truncate">{family.title}</h3>
              {family.description && (
                <p className="text-xs text-neutral-400 mt-1 line-clamp-2">
                  {family.description}
                </p>
              )}
              <p className="text-xs text-neutral-500 mt-2">
                {family.member_count} {family.member_count === 1 ? "repository" : "repositories"}
              </p>
            </button>
          ))}
        </div>
      )}
    </aside>
  );
}

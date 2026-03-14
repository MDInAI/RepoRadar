'use client';

interface Repository {
  id: number;
  full_name: string;
  stars: number;
}

interface ObsessionScopePanelProps {
  familyTitle: string | null;
  repositories: Repository[];
  ideaFamilyId: number | null;
  scopeUpdatedAt: string | null;
  onViewFamily?: () => void;
}

export function ObsessionScopePanel({ familyTitle, repositories, ideaFamilyId, scopeUpdatedAt, onViewFamily }: ObsessionScopePanelProps) {
  return (
    <div className="space-y-2">
      <div className="text-sm font-medium text-gray-700">Scope</div>
      <div className="border rounded p-3">
        {familyTitle && (
          <div className="flex justify-between items-center mb-2">
            <div className="font-medium text-sm">{familyTitle}</div>
            {onViewFamily && (
              <button onClick={onViewFamily} className="text-sm text-blue-600 hover:text-blue-800">
                View Family
              </button>
            )}
          </div>
        )}
        <div className="text-xs text-gray-600 mb-2">{repositories.length} repositories</div>
        <div className="space-y-1 max-h-32 overflow-y-auto">
          {repositories.map((repo) => (
            <div key={repo.id} className="flex justify-between text-xs">
              <span className="text-gray-700">{repo.full_name}</span>
              <span className="text-gray-500">⭐ {repo.stars}</span>
            </div>
          ))}
        </div>
        {scopeUpdatedAt && (
          <div className="text-xs text-gray-500 mt-2">
            Updated: {new Date(scopeUpdatedAt).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  );
}

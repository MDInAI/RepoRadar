'use client';

interface ObsessionContextActionsProps {
  status: string;
  onViewDetails: () => void;
  onTriggerRefresh: () => void;
  onPause: () => void;
  onResume: () => void;
  onMarkComplete: () => void;
  onDelete: () => void;
}

export function ObsessionContextActions({
  status,
  onViewDetails,
  onTriggerRefresh,
  onPause,
  onResume,
  onMarkComplete,
  onDelete,
}: ObsessionContextActionsProps) {
  const handleDelete = () => {
    if (confirm('Are you sure you want to delete this Obsession context?')) {
      onDelete();
    }
  };

  return (
    <div className="flex gap-1">
      <button onClick={onViewDetails} className="px-2 py-1 text-xs border rounded hover:bg-gray-50">
        View Details
      </button>
      <button onClick={onTriggerRefresh} className="px-2 py-1 text-xs border rounded hover:bg-gray-50">
        Trigger Refresh
      </button>
      {status === 'active' && (
        <button onClick={onPause} className="px-2 py-1 text-xs border rounded hover:bg-gray-50">
          Pause
        </button>
      )}
      {status === 'paused' && (
        <button onClick={onResume} className="px-2 py-1 text-xs border rounded hover:bg-gray-50">
          Resume
        </button>
      )}
      {status !== 'completed' && (
        <button onClick={onMarkComplete} className="px-2 py-1 text-xs border rounded hover:bg-gray-50">
          Mark Complete
        </button>
      )}
      <button onClick={handleDelete} className="px-2 py-1 text-xs border rounded hover:bg-red-50 text-red-600">
        Delete
      </button>
    </div>
  );
}

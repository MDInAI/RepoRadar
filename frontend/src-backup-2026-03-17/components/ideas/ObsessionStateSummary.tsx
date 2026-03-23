'use client';

interface ObsessionStateSummaryProps {
  totalRuns: number;
  successfulRuns: number;
  failedRuns: number;
  memorySegments: number;
  status: string;
  refreshPolicy: string;
  onTriggerRefresh: () => void;
  onToggleStatus: () => void;
  onEdit: () => void;
  isRefreshing?: boolean;
  isUpdating?: boolean;
}

export function ObsessionStateSummary({
  totalRuns,
  successfulRuns,
  failedRuns,
  memorySegments,
  status,
  refreshPolicy,
  onTriggerRefresh,
  onToggleStatus,
  onEdit,
  isRefreshing,
  isUpdating,
}: ObsessionStateSummaryProps) {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-500';
      case 'paused': return 'bg-yellow-500';
      case 'completed': return 'bg-gray-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        <div className="border rounded p-3">
          <div className="text-xs text-gray-600">Total Runs</div>
          <div className="text-2xl font-semibold">{totalRuns}</div>
        </div>
        <div className="border rounded p-3">
          <div className="text-xs text-gray-600">Successful</div>
          <div className="text-2xl font-semibold text-green-600">{successfulRuns}</div>
        </div>
        <div className="border rounded p-3">
          <div className="text-xs text-gray-600">Failed</div>
          <div className="text-2xl font-semibold text-red-600">{failedRuns}</div>
        </div>
        <div className="border rounded p-3">
          <div className="text-xs text-gray-600">Memory Segments</div>
          <div className="text-2xl font-semibold">{memorySegments}</div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className={`w-3 h-3 rounded-full ${getStatusColor(status)}`}></div>
          <span className="text-sm font-medium">{status}</span>
        </div>
        <span className="text-sm text-gray-600">•</span>
        <span className="text-sm text-gray-600">
          Refresh: {refreshPolicy}
          {refreshPolicy !== 'manual' && ' • Next: scheduled by backend'}
        </span>
      </div>

      <div className="flex gap-2">
        <button
          onClick={onTriggerRefresh}
          disabled={isRefreshing}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {isRefreshing ? 'Triggering...' : 'Trigger Refresh'}
        </button>
        <button
          onClick={onToggleStatus}
          disabled={isUpdating || status === 'completed'}
          className="px-3 py-1.5 text-sm border rounded hover:bg-gray-50 disabled:opacity-50"
        >
          {status === 'active' ? 'Pause' : 'Resume'}
        </button>
        <button onClick={onEdit} className="px-3 py-1.5 text-sm border rounded hover:bg-gray-50">
          Edit Settings
        </button>
      </div>
    </div>
  );
}

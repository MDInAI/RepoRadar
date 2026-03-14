'use client';

interface SynthesisRun {
  id: number;
  run_type: string;
  status: string;
  title: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

interface SynthesisRunTimelineProps {
  runs: SynthesisRun[];
  onViewOutput: (runId: number) => void;
}

export function SynthesisRunTimeline({ runs, onViewOutput }: SynthesisRunTimelineProps) {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'text-green-600';
      case 'running': return 'text-blue-600';
      case 'failed': return 'text-red-600';
      case 'pending': return 'text-gray-600';
      default: return 'text-gray-600';
    }
  };

  const calculateDuration = (startedAt: string | null, completedAt: string | null) => {
    if (!startedAt || !completedAt) return null;
    const duration = new Date(completedAt).getTime() - new Date(startedAt).getTime();
    const seconds = Math.floor(duration / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    return `${minutes}m ${seconds % 60}s`;
  };

  const successCount = runs.filter(r => r.status === 'completed').length;
  const successRate = runs.length > 0 ? Math.round((successCount / runs.length) * 100) : 0;

  return (
    <div className="space-y-3">
      <div className="flex gap-4 text-sm">
        <span className="text-gray-600">Total Runs: {runs.length}</span>
        <span className="text-gray-600">Success Rate: {successRate}%</span>
      </div>

      {runs.length === 0 ? (
        <div className="text-sm text-gray-500">No synthesis runs yet</div>
      ) : (
        <div className="space-y-2">
          {runs.map((run) => (
            <div key={run.id} className="border rounded p-3">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="font-medium text-sm">{run.title || `Run #${run.id}`}</div>
                  <div className="flex gap-3 mt-1 text-xs text-gray-600">
                    <span className={getStatusColor(run.status)}>{run.status}</span>
                    <span>{run.run_type}</span>
                    {calculateDuration(run.started_at, run.completed_at) && (
                      <span>{calculateDuration(run.started_at, run.completed_at)}</span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {new Date(run.created_at).toLocaleString()}
                  </div>
                </div>
                <button
                  onClick={() => onViewOutput(run.id)}
                  className="text-sm text-blue-600 hover:text-blue-800"
                >
                  View Output
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

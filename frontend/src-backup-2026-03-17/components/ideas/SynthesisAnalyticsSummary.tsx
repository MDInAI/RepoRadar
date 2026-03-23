"use client";

import { useSynthesisRuns } from "@/hooks/useSynthesis";
import { useQuery } from "@tanstack/react-query";
import { fetchRepositoryDetail } from "@/api/repositories";

interface SynthesisAnalyticsSummaryProps {
  familyId: number;
}

export function SynthesisAnalyticsSummary({ familyId }: SynthesisAnalyticsSummaryProps) {
  const { data: runs } = useSynthesisRuns(familyId);

  // Most-used repositories calculation (needed for useQuery)
  const repoUsage = new Map<number, number>();
  (runs || []).forEach(r => {
    r.input_repository_ids.forEach(id => {
      repoUsage.set(id, (repoUsage.get(id) || 0) + 1);
    });
  });
  const topRepos = Array.from(repoUsage.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);
  const topRepoIds = topRepos.map(([id]) => id);

  // Fetch repository details for top repos (must be called unconditionally)
  const { data: repoDetails } = useQuery({
    queryKey: ["analytics-repos", topRepoIds],
    queryFn: async () => {
      const details = await Promise.all(
        topRepoIds.map(id => fetchRepositoryDetail(id).catch(() => null))
      );
      return Object.fromEntries(topRepoIds.map((id, idx) => [id, details[idx]]));
    },
    enabled: topRepoIds.length > 0,
  });

  if (!runs || runs.length === 0) return null;

  const totalRuns = runs.length;
  const completedRuns = runs.filter(r => r.status === "completed").length;
  const successRate = totalRuns > 0 ? Math.round((completedRuns / totalRuns) * 100) : 0;

  // Average completion time
  const completedWithTimes = runs.filter(r => r.started_at && r.completed_at);
  const avgCompletionMs = completedWithTimes.length > 0
    ? completedWithTimes.reduce((sum, r) => {
        const start = new Date(r.started_at!).getTime();
        const end = new Date(r.completed_at!).getTime();
        return sum + (end - start);
      }, 0) / completedWithTimes.length
    : 0;
  const avgCompletionMin = Math.round(avgCompletionMs / 60000);

  const getRepoName = (id: number) => repoDetails?.[id]?.full_name || `Repo #${id}`;

  // Activity timeline (runs per day, last 7 days) - use local dates consistently
  const now = new Date();
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  const dailyActivity = new Map<string, number>();

  for (let i = 0; i < 7; i++) {
    const date = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
    const dateKey = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().split("T")[0];
    dailyActivity.set(dateKey, 0);
  }

  runs.forEach(r => {
    const runDate = new Date(r.created_at);
    if (runDate >= sevenDaysAgo) {
      const dateKey = new Date(runDate.getTime() - runDate.getTimezoneOffset() * 60000).toISOString().split("T")[0];
      dailyActivity.set(dateKey, (dailyActivity.get(dateKey) || 0) + 1);
    }
  });

  const timelineData = Array.from(dailyActivity.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([date, count]) => ({ date, count }));

  const maxCount = Math.max(...timelineData.map(d => d.count), 1);

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded p-4">
      <h4 className="text-sm font-semibold text-neutral-300 mb-3">Analytics</h4>
      <div className="grid grid-cols-3 gap-4 text-center mb-4">
        <div>
          <div className="text-2xl font-bold text-neutral-100">{totalRuns}</div>
          <div className="text-xs text-neutral-500">Total Runs</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-green-400">{successRate}%</div>
          <div className="text-xs text-neutral-500">Success Rate</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-neutral-100">{avgCompletionMin}m</div>
          <div className="text-xs text-neutral-500">Avg Time</div>
        </div>
      </div>
      {topRepos.length > 0 && (
        <div className="border-t border-neutral-800 pt-3 mt-3">
          <div className="text-xs text-neutral-500 mb-2">Most-Used Repositories</div>
          <div className="space-y-1">
            {topRepos.map(([repoId, count]) => (
              <div key={repoId} className="flex justify-between text-xs">
                <span className="text-neutral-400 truncate">{getRepoName(repoId)}</span>
                <span className="text-neutral-300">{count} runs</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="border-t border-neutral-800 pt-3 mt-3">
        <div className="text-xs text-neutral-500 mb-2">Activity Timeline (Last 7 Days)</div>
        <div className="flex items-end gap-1 h-16">
          {timelineData.map(({ date, count }) => (
            <div key={date} className="flex-1 flex flex-col items-center gap-1">
              <div
                className="w-full bg-blue-600 rounded-t"
                style={{ height: `${(count / maxCount) * 100}%` }}
                title={`${date}: ${count} runs`}
              />
              <div className="text-[10px] text-neutral-600">
                {new Date(date + "T12:00:00").getDate()}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

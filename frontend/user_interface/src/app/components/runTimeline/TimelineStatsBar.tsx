/** Stats summary bar for the run timeline. */
import type { TimelineStats } from "./types";

type Props = {
  stats: TimelineStats;
};

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex flex-col items-center">
      <span className={`text-lg font-semibold tabular-nums ${color || "text-zinc-200"}`}>
        {value}
      </span>
      <span className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</span>
    </div>
  );
}

export function TimelineStatsBar({ stats }: Props) {
  const avgSec = stats.avg_duration_ms > 0 ? `${(stats.avg_duration_ms / 1000).toFixed(1)}s` : "—";
  const cost = stats.total_cost_usd > 0 ? `$${stats.total_cost_usd.toFixed(2)}` : "$0";

  return (
    <div className="flex items-center justify-around px-4 py-3 border-b border-zinc-800 bg-zinc-900/60">
      <Stat label="Total" value={String(stats.total_runs)} />
      <Stat label="Running" value={String(stats.running)} color="text-violet-400" />
      <Stat label="Completed" value={String(stats.completed)} color="text-emerald-400" />
      <Stat label="Failed" value={String(stats.failed)} color="text-red-400" />
      <Stat label="Avg Duration" value={avgSec} />
      <Stat label="Total Cost" value={cost} color="text-amber-400" />
    </div>
  );
}

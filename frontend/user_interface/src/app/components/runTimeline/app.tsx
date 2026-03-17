/** RunTimeline — central run timeline panel.
 *
 * Shows a unified view of all agent runs, workflow runs, scheduled runs, and
 * event-triggered runs with filtering, stats, and expandable detail rows.
 */
import { useCallback, useEffect, useState } from "react";
import { RefreshCw, X } from "lucide-react";
import type { RunTimelineEntry, TimelineFilters, TimelineStats } from "./types";
import { TimelineFiltersBar } from "./TimelineFiltersBar";
import { TimelineStatsBar } from "./TimelineStatsBar";
import { TimelineRow } from "./TimelineRow";
import { fetchApi } from "../../../api/client/core";

type Props = {
  open: boolean;
  onClose: () => void;
};

function computeStats(entries: RunTimelineEntry[]): TimelineStats {
  const running = entries.filter((e) => e.status === "running").length;
  const completed = entries.filter((e) => e.status === "completed").length;
  const failed = entries.filter((e) => e.status === "failed").length;
  const totalCost = entries.reduce((s, e) => s + (e.cost_usd ?? 0), 0);
  const durations = entries.filter((e) => e.duration_ms != null).map((e) => e.duration_ms!);
  const avgDuration = durations.length > 0 ? durations.reduce((a, b) => a + b, 0) / durations.length : 0;
  return {
    total_runs: entries.length,
    running,
    completed,
    failed,
    total_cost_usd: totalCost,
    avg_duration_ms: avgDuration,
  };
}

export function RunTimeline({ open, onClose }: Props) {
  const [entries, setEntries] = useState<RunTimelineEntry[]>([]);
  const [filters, setFilters] = useState<TimelineFilters>({});
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchRuns = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.type) params.set("type", filters.type);
      if (filters.status) params.set("status", filters.status);
      if (filters.trigger) params.set("trigger_type", filters.trigger);
      if (filters.since) params.set("since", String(filters.since));
      if (filters.until) params.set("until", String(filters.until));
      params.set("limit", "100");
      const qs = params.toString();
      const resp = await fetchApi(`/api/observability/timeline${qs ? `?${qs}` : ""}`);
      if (resp.ok) {
        const data = (await resp.json()) as RunTimelineEntry[];
        setEntries(data);
      }
    } catch {
      // silently fail — panel is informational
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    if (open) {
      fetchRuns();
    }
  }, [open, fetchRuns]);

  // Auto-refresh every 10s when panel is open
  useEffect(() => {
    if (!open) return;
    const interval = setInterval(fetchRuns, 10_000);
    return () => clearInterval(interval);
  }, [open, fetchRuns]);

  if (!open) return null;

  const stats = computeStats(entries);

  return (
    <div className="fixed inset-y-0 right-0 w-[520px] bg-zinc-950 border-l border-zinc-800 z-50 flex flex-col shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <h2 className="text-sm font-semibold text-zinc-200">Run Timeline</h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={fetchRuns}
            disabled={loading}
            className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Stats */}
      <TimelineStatsBar stats={stats} />

      {/* Filters */}
      <TimelineFiltersBar filters={filters} onChange={setFilters} />

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {entries.length === 0 && !loading && (
          <div className="flex items-center justify-center h-32 text-zinc-500 text-sm">
            No runs found
          </div>
        )}
        {entries.map((entry) => (
          <TimelineRow
            key={entry.id}
            entry={entry}
            isExpanded={expandedId === entry.id}
            onToggle={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
          />
        ))}
      </div>
    </div>
  );
}

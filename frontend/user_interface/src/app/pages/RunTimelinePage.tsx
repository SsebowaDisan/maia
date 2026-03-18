import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Loader2,
  PlayCircle,
  RefreshCw,
  Workflow,
  Zap,
} from "lucide-react";
import { fetchApi } from "../../api/client/core";
import type {
  RunTimelineEntry,
  TimelineFilters,
  TimelineStats,
} from "../components/runTimeline/types";

// ── Helpers ──────────────────────────────────────────────────────────────────

function computeStats(entries: RunTimelineEntry[]): TimelineStats {
  const running = entries.filter((e) => e.status === "running").length;
  const completed = entries.filter((e) => e.status === "completed").length;
  const failed = entries.filter((e) => e.status === "failed").length;
  const totalCost = entries.reduce((s, e) => s + (e.cost_usd ?? 0), 0);
  const durations = entries
    .filter((e) => e.duration_ms != null)
    .map((e) => e.duration_ms!);
  const avgDuration =
    durations.length > 0
      ? durations.reduce((a, b) => a + b, 0) / durations.length
      : 0;
  return {
    total_runs: entries.length,
    running,
    completed,
    failed,
    total_cost_usd: totalCost,
    avg_duration_ms: avgDuration,
  };
}

function formatDuration(ms?: number): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatCost(usd?: number): string {
  if (usd == null || usd === 0) return "—";
  return `$${usd.toFixed(4)}`;
}

// ── Status / type config ─────────────────────────────────────────────────────

const STATUS_CONF: Record<
  string,
  { icon: React.ReactNode; label: string; dotColor: string }
> = {
  running: {
    icon: <Loader2 className="h-4 w-4 text-[#7c3aed] animate-spin" />,
    label: "Running",
    dotColor: "bg-[#7c3aed]",
  },
  completed: {
    icon: <CheckCircle2 className="h-4 w-4 text-[#16a34a]" />,
    label: "Completed",
    dotColor: "bg-[#16a34a]",
  },
  failed: {
    icon: <AlertCircle className="h-4 w-4 text-[#dc2626]" />,
    label: "Failed",
    dotColor: "bg-[#dc2626]",
  },
  cancelled: {
    icon: <Clock className="h-4 w-4 text-[#98a2b3]" />,
    label: "Cancelled",
    dotColor: "bg-[#98a2b3]",
  },
  queued: {
    icon: <Clock className="h-4 w-4 text-[#f59e0b]" />,
    label: "Queued",
    dotColor: "bg-[#f59e0b]",
  },
};

const TYPE_CONF: Record<string, { icon: React.ReactNode; label: string }> = {
  agent_run: {
    icon: <Activity className="h-3.5 w-3.5 text-[#7c3aed]" />,
    label: "Agent",
  },
  workflow_run: {
    icon: <Workflow className="h-3.5 w-3.5 text-[#0ea5e9]" />,
    label: "Workflow",
  },
  scheduled_run: {
    icon: <Clock className="h-3.5 w-3.5 text-[#f59e0b]" />,
    label: "Scheduled",
  },
  event_run: {
    icon: <Zap className="h-3.5 w-3.5 text-[#f97316]" />,
    label: "Event",
  },
};

// ── Filter selects ───────────────────────────────────────────────────────────

const STATUS_OPTIONS = ["all", "running", "completed", "failed", "queued"];
const TYPE_OPTIONS = [
  "all",
  "agent_run",
  "workflow_run",
  "scheduled_run",
  "event_run",
];
const TRIGGER_OPTIONS = ["all", "manual", "scheduled", "event", "webhook"];

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex items-center gap-1.5 text-[12px] font-medium text-[#475467]">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-black/[0.1] bg-white px-2.5 py-1.5 text-[12px] text-[#111827] focus:outline-none focus:ring-2 focus:ring-[#7c3aed]/25 focus:border-[#7c3aed]/40"
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt === "all"
              ? "All"
              : opt
                  .replace(/_/g, " ")
                  .replace(/\b\w/g, (c) => c.toUpperCase())}
          </option>
        ))}
      </select>
    </label>
  );
}

// ── Stat card ────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-black/[0.06] bg-white px-5 py-3 shadow-sm">
      <span
        className={`text-[22px] font-bold tabular-nums tracking-tight ${accent || "text-[#111827]"}`}
      >
        {value}
      </span>
      <span className="mt-0.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-[#98a2b3]">
        {label}
      </span>
    </div>
  );
}

// ── Row ──────────────────────────────────────────────────────────────────────

function RunRow({
  entry,
  isExpanded,
  onToggle,
}: {
  entry: RunTimelineEntry;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const status = STATUS_CONF[entry.status] ?? STATUS_CONF.queued;
  const type = TYPE_CONF[entry.type] ?? TYPE_CONF.agent_run;

  return (
    <div
      className={`border-b border-black/[0.04] last:border-b-0 transition-colors ${isExpanded ? "bg-[#f9fafb]" : ""}`}
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-5 py-3.5 text-left transition-colors hover:bg-[#f5f3ff]/40"
      >
        <span className="shrink-0">{status.icon}</span>

        <span className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.06] bg-[#f8fafc] px-2 py-0.5 text-[10px] font-medium text-[#475467]">
          {type.icon}
          {type.label}
        </span>

        <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-[#111827]">
          {entry.name}
        </span>

        <span className="w-16 text-right text-[12px] tabular-nums text-[#667085]">
          {formatDuration(entry.duration_ms)}
        </span>
        <span className="w-16 text-right text-[12px] tabular-nums text-[#667085]">
          {formatCost(entry.cost_usd)}
        </span>
        <span className="w-28 text-right text-[11px] tabular-nums text-[#98a2b3]">
          {formatTime(entry.started_at)}
        </span>

        {isExpanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[#98a2b3]" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[#98a2b3]" />
        )}
      </button>

      {isExpanded ? (
        <div className="px-5 pb-4 pt-1">
          <div className="rounded-xl border border-black/[0.06] bg-white p-4">
            <div className="grid max-w-lg grid-cols-2 gap-x-8 gap-y-2 text-[12px]">
              <span className="text-[#667085]">Run ID</span>
              <span className="font-mono text-[#111827]">
                {entry.id.slice(0, 16)}…
              </span>
              <span className="text-[#667085]">Trigger</span>
              <span className="text-[#111827] capitalize">{entry.trigger}</span>
              <span className="text-[#667085]">Tokens</span>
              <span className="tabular-nums text-[#111827]">
                {entry.tokens_in ?? 0} in / {entry.tokens_out ?? 0} out
              </span>
              <span className="text-[#667085]">Tool calls</span>
              <span className="tabular-nums text-[#111827]">
                {entry.tool_calls ?? 0}
              </span>
              {entry.step_count != null ? (
                <>
                  <span className="text-[#667085]">Steps</span>
                  <span className="tabular-nums text-[#111827]">
                    {entry.steps_completed ?? 0}/{entry.step_count}
                  </span>
                </>
              ) : null}
            </div>
            {entry.error ? (
              <div className="mt-3 rounded-lg border border-[#fecaca] bg-[#fff1f2] p-3 font-mono text-[11px] leading-relaxed text-[#b42318] whitespace-pre-wrap">
                {entry.error}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function RunTimelinePage() {
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
      params.set("limit", "200");
      const qs = params.toString();
      const resp = await fetchApi(
        `/api/observability/timeline${qs ? `?${qs}` : ""}`,
      );
      if (resp.ok) {
        const data = (await resp.json()) as RunTimelineEntry[];
        setEntries(data);
      }
    } catch {
      // Keep page stable when API is unavailable.
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  // Auto-refresh every 10s.
  useEffect(() => {
    const interval = setInterval(fetchRuns, 10_000);
    return () => clearInterval(interval);
  }, [fetchRuns]);

  const stats = computeStats(entries);
  const avgSec =
    stats.avg_duration_ms > 0
      ? `${(stats.avg_duration_ms / 1000).toFixed(1)}s`
      : "—";
  const costStr =
    stats.total_cost_usd > 0 ? `$${stats.total_cost_usd.toFixed(2)}` : "$0";

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="shrink-0 px-8 pt-8 pb-0">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7c3aed]">
          Workspace
        </p>
        <div className="mt-1 flex items-center justify-between">
          <h1 className="text-[28px] font-semibold tracking-tight text-[#111827]">
            Timeline
          </h1>
          <button
            type="button"
            onClick={fetchRuns}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.08] bg-white px-3.5 py-1.5 text-[12px] font-medium text-[#344054] shadow-sm transition-colors hover:bg-[#f9fafb] disabled:opacity-50"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`}
            />
            Refresh
          </button>
        </div>
        <p className="mt-1.5 text-[14px] leading-relaxed text-[#667085]">
          View a unified timeline of all agent runs, workflow runs, and
          scheduled tasks.
        </p>
      </div>

      {/* Stats row */}
      <div className="shrink-0 px-8 pt-6 pb-4">
        <div className="flex flex-wrap gap-3">
          <StatCard label="Total" value={String(stats.total_runs)} />
          <StatCard
            label="Running"
            value={String(stats.running)}
            accent="text-[#7c3aed]"
          />
          <StatCard
            label="Completed"
            value={String(stats.completed)}
            accent="text-[#16a34a]"
          />
          <StatCard
            label="Failed"
            value={String(stats.failed)}
            accent="text-[#dc2626]"
          />
          <StatCard label="Avg Duration" value={avgSec} />
          <StatCard
            label="Total Cost"
            value={costStr}
            accent="text-[#f59e0b]"
          />
        </div>
      </div>

      {/* Filters */}
      <div className="shrink-0 flex items-center gap-5 px-8 pb-4">
        <FilterSelect
          label="Status"
          value={filters.status || "all"}
          options={STATUS_OPTIONS}
          onChange={(v) =>
            setFilters({ ...filters, status: v === "all" ? undefined : v })
          }
        />
        <FilterSelect
          label="Type"
          value={filters.type || "all"}
          options={TYPE_OPTIONS}
          onChange={(v) =>
            setFilters({ ...filters, type: v === "all" ? undefined : v })
          }
        />
        <FilterSelect
          label="Trigger"
          value={filters.trigger || "all"}
          options={TRIGGER_OPTIONS}
          onChange={(v) =>
            setFilters({ ...filters, trigger: v === "all" ? undefined : v })
          }
        />
      </div>

      {/* Run list */}
      <div className="min-h-0 flex-1 overflow-y-auto px-8 pb-8">
        <div className="overflow-hidden rounded-2xl border border-black/[0.06] bg-white shadow-sm">
          {/* Column headers */}
          <div className="flex items-center gap-3 border-b border-black/[0.06] bg-[#f9fafb] px-5 py-2.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-[#98a2b3]">
            <span className="w-5" />
            <span className="w-20">Type</span>
            <span className="min-w-0 flex-1">Name</span>
            <span className="w-16 text-right">Duration</span>
            <span className="w-16 text-right">Cost</span>
            <span className="w-28 text-right">Started</span>
            <span className="w-3.5" />
          </div>

          {loading && entries.length === 0 ? (
            <div className="flex items-center justify-center gap-2 py-16 text-[13px] text-[#667085]">
              <Loader2 className="h-4 w-4 animate-spin text-[#7c3aed]" />
              Loading runs…
            </div>
          ) : null}

          {!loading && entries.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-[#f5f3ff]">
                <PlayCircle className="h-6 w-6 text-[#7c3aed]" />
              </div>
              <p className="text-[14px] font-medium text-[#344054]">
                No runs found
              </p>
              <p className="mt-1 text-[12px] text-[#98a2b3]">
                Runs will appear here as agents and workflows execute.
              </p>
            </div>
          ) : null}

          {entries.map((entry) => (
            <RunRow
              key={entry.id}
              entry={entry}
              isExpanded={expandedId === entry.id}
              onToggle={() =>
                setExpandedId(expandedId === entry.id ? null : entry.id)
              }
            />
          ))}
        </div>
      </div>
    </div>
  );
}

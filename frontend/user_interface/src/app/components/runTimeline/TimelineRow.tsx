/** Single row in the run timeline list. */
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  PlayCircle,
  Workflow,
  Zap,
} from "lucide-react";
import type { RunTimelineEntry } from "./types";

const statusIcons: Record<string, React.ReactNode> = {
  running: <Loader2 className="h-4 w-4 text-violet-500 animate-spin" />,
  completed: <CheckCircle2 className="h-4 w-4 text-emerald-500" />,
  failed: <AlertCircle className="h-4 w-4 text-red-500" />,
  cancelled: <Clock className="h-4 w-4 text-zinc-400" />,
  queued: <Clock className="h-4 w-4 text-amber-400" />,
};

const typeIcons: Record<string, React.ReactNode> = {
  agent_run: <Activity className="h-4 w-4 text-violet-400" />,
  workflow_run: <Workflow className="h-4 w-4 text-sky-400" />,
  scheduled_run: <Clock className="h-4 w-4 text-amber-400" />,
  event_run: <Zap className="h-4 w-4 text-orange-400" />,
};

function formatDuration(ms?: number): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatCost(usd?: number): string {
  if (usd == null || usd === 0) return "—";
  return `$${usd.toFixed(4)}`;
}

type Props = {
  entry: RunTimelineEntry;
  isExpanded: boolean;
  onToggle: () => void;
};

export function TimelineRow({ entry, isExpanded, onToggle }: Props) {
  return (
    <div className="border-b border-zinc-800 last:border-b-0">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-zinc-800/50 transition-colors text-left"
      >
        {statusIcons[entry.status] ?? <PlayCircle className="h-4 w-4 text-zinc-500" />}
        {typeIcons[entry.type] ?? <Activity className="h-4 w-4 text-zinc-500" />}

        <span className="flex-1 text-sm font-medium text-zinc-200 truncate">
          {entry.name}
        </span>

        <span className="text-xs text-zinc-500 tabular-nums w-16 text-right">
          {formatDuration(entry.duration_ms)}
        </span>

        <span className="text-xs text-zinc-500 tabular-nums w-16 text-right">
          {formatCost(entry.cost_usd)}
        </span>

        <span className="text-xs text-zinc-500 tabular-nums w-20 text-right">
          {formatTime(entry.started_at)}
        </span>
      </button>

      {isExpanded && (
        <div className="px-4 pb-3 text-xs text-zinc-400 space-y-1 bg-zinc-900/50">
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 max-w-md">
            <span>Run ID</span>
            <span className="text-zinc-300 font-mono">{entry.id.slice(0, 12)}…</span>
            <span>Trigger</span>
            <span className="text-zinc-300">{entry.trigger}</span>
            <span>Tokens</span>
            <span className="text-zinc-300 tabular-nums">
              {entry.tokens_in ?? 0} in / {entry.tokens_out ?? 0} out
            </span>
            <span>Tool calls</span>
            <span className="text-zinc-300 tabular-nums">{entry.tool_calls ?? 0}</span>
            {entry.step_count != null && (
              <>
                <span>Steps</span>
                <span className="text-zinc-300 tabular-nums">
                  {entry.steps_completed ?? 0}/{entry.step_count}
                </span>
              </>
            )}
          </div>
          {entry.error && (
            <div className="mt-2 p-2 rounded bg-red-950/40 border border-red-900/50 text-red-300 font-mono whitespace-pre-wrap">
              {entry.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

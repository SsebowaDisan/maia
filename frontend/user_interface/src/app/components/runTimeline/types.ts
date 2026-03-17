/** Types for the central run timeline component. */

type RunTimelineEntry = {
  id: string;
  type: "agent_run" | "workflow_run" | "scheduled_run" | "event_run";
  name: string;
  agent_id?: string;
  workflow_id?: string;
  status: "running" | "completed" | "failed" | "cancelled" | "queued";
  trigger: "manual" | "scheduled" | "event" | "webhook";
  started_at: number;
  ended_at?: number | null;
  duration_ms?: number;
  tokens_in?: number;
  tokens_out?: number;
  tool_calls?: number;
  cost_usd?: number;
  error?: string | null;
  step_count?: number;
  steps_completed?: number;
};

type TimelineFilters = {
  type?: string;
  status?: string;
  trigger?: string;
  agent_id?: string;
  since?: number;
  until?: number;
};

type TimelineStats = {
  total_runs: number;
  running: number;
  completed: number;
  failed: number;
  total_cost_usd: number;
  avg_duration_ms: number;
};

export type { RunTimelineEntry, TimelineFilters, TimelineStats };

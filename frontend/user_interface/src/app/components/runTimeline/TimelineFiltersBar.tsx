/** Filter bar for the run timeline. */
import type { TimelineFilters } from "./types";

type Props = {
  filters: TimelineFilters;
  onChange: (filters: TimelineFilters) => void;
};

const statusOptions = ["all", "running", "completed", "failed", "queued"];
const typeOptions = ["all", "agent_run", "workflow_run", "scheduled_run", "event_run"];
const triggerOptions = ["all", "manual", "scheduled", "event", "webhook"];

function Select({
  value,
  options,
  onChange,
  label,
}: {
  value: string;
  options: string[];
  onChange: (v: string) => void;
  label: string;
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-zinc-400">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 text-xs focus:outline-none focus:ring-1 focus:ring-violet-500"
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt === "all" ? "All" : opt.replace("_", " ")}
          </option>
        ))}
      </select>
    </label>
  );
}

export function TimelineFiltersBar({ filters, onChange }: Props) {
  return (
    <div className="flex items-center gap-4 px-4 py-2 border-b border-zinc-800 bg-zinc-900/80">
      <Select
        label="Status"
        value={filters.status || "all"}
        options={statusOptions}
        onChange={(v) => onChange({ ...filters, status: v === "all" ? undefined : v })}
      />
      <Select
        label="Type"
        value={filters.type || "all"}
        options={typeOptions}
        onChange={(v) => onChange({ ...filters, type: v === "all" ? undefined : v })}
      />
      <Select
        label="Trigger"
        value={filters.trigger || "all"}
        options={triggerOptions}
        onChange={(v) => onChange({ ...filters, trigger: v === "all" ? undefined : v })}
      />
    </div>
  );
}

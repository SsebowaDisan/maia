import type { AgentActivityEvent } from "../../types";
import {
  EVT_ASSEMBLY_COMPLETED,
  EVT_ASSEMBLY_COMPLETE,
  EVT_ASSEMBLY_EDGE_ADDED,
  EVT_ASSEMBLY_ERROR,
  EVT_ASSEMBLY_STARTED,
  EVT_ASSEMBLY_STEP_ADDED,
  EVT_EXECUTION_STARTING,
} from "../../constants/eventTypes";

type AssemblyProgressPanelProps = {
  events: AgentActivityEvent[];
  activeEvent: AgentActivityEvent | null;
};

type AssemblyRow = {
  id: string;
  type: string;
  title: string;
  detail: string;
};

function toRows(events: AgentActivityEvent[]): AssemblyRow[] {
  const rows: AssemblyRow[] = [];
  for (const event of events) {
    const type = String(event.event_type || "").trim().toLowerCase();
    if (
      type !== EVT_ASSEMBLY_STARTED &&
      type !== EVT_ASSEMBLY_STEP_ADDED &&
      type !== EVT_ASSEMBLY_EDGE_ADDED &&
      type !== EVT_ASSEMBLY_COMPLETE &&
      type !== EVT_ASSEMBLY_COMPLETED &&
      type !== EVT_ASSEMBLY_ERROR &&
      type !== EVT_EXECUTION_STARTING &&
      type !== "workflow_saved"
    ) {
      continue;
    }
    rows.push({
      id: String(event.event_id || `${type}-${event.timestamp}`),
      type,
      title: String(event.title || type.replace(/_/g, " ")).trim(),
      detail: String(event.detail || "").trim(),
    });
  }
  return rows;
}

function statusLabel(rows: AssemblyRow[]): string {
  const hasError = rows.some((row) => row.type === EVT_ASSEMBLY_ERROR);
  if (hasError) {
    return "Assembly error";
  }
  const executionStarted = rows.some((row) => row.type === EVT_EXECUTION_STARTING);
  if (executionStarted) {
    return "Execution started";
  }
  const completed = rows.some((row) => row.type === EVT_ASSEMBLY_COMPLETE || row.type === EVT_ASSEMBLY_COMPLETED);
  if (completed) {
    return "Assembly complete";
  }
  return "Assembling workflow";
}

function statusClass(rows: AssemblyRow[]): string {
  const hasError = rows.some((row) => row.type === EVT_ASSEMBLY_ERROR);
  if (hasError) {
    return "bg-[#fef2f2] text-[#991b1b] border-[#fecaca]";
  }
  const executionStarted = rows.some((row) => row.type === EVT_EXECUTION_STARTING);
  if (executionStarted) {
    return "bg-[#ecfdf3] text-[#166534] border-[#bbf7d0]";
  }
  return "bg-[#eff6ff] text-[#1d4ed8] border-[#bfdbfe]";
}

function eventTone(type: string): string {
  if (type === EVT_ASSEMBLY_ERROR) {
    return "border-[#fecaca] bg-[#fff1f2]";
  }
  if (type === EVT_EXECUTION_STARTING) {
    return "border-[#bbf7d0] bg-[#f0fdf4]";
  }
  return "border-[#dbeafe] bg-white";
}

export function AssemblyProgressPanel({ events, activeEvent }: AssemblyProgressPanelProps) {
  const rows = toRows(events);
  if (!rows.length) {
    return null;
  }

  const stepCount = rows.filter((row) => row.type === EVT_ASSEMBLY_STEP_ADDED).length;
  const edgeCount = rows.filter((row) => row.type === EVT_ASSEMBLY_EDGE_ADDED).length;
  const latestRows = rows.slice(-5);
  const liveType = String(activeEvent?.event_type || "").trim().toLowerCase();
  const isLiveAssembly = liveType.startsWith("assembly_");

  return (
    <section className="mt-3 rounded-2xl border border-[#dbeafe] bg-[linear-gradient(180deg,#eff6ff_0%,#f8fbff_100%)] px-4 py-3">
      <div className="flex items-center gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#1d4ed8]">
          Workflow assembly
        </p>
        <span className={`ml-auto rounded-full border px-2 py-0.5 text-[10px] font-semibold ${statusClass(rows)}`}>
          {statusLabel(rows)}
        </span>
      </div>
      <p className="mt-1 text-[12px] text-[#334155]">
        {stepCount} steps, {edgeCount} links generated.
        {rows.some((row) => row.type === EVT_EXECUTION_STARTING)
          ? " Moving from planning into live execution."
          : ""}
      </p>

      <div className="mt-2 space-y-1.5">
        {latestRows.map((row) => (
          <article key={row.id} className={`rounded-xl border px-3 py-2 ${eventTone(row.type)}`}>
            <p className="text-[12px] font-medium text-[#0f172a]">{row.title}</p>
            {row.detail ? (
              <p className="mt-0.5 text-[11px] text-[#475467]">{row.detail}</p>
            ) : null}
          </article>
        ))}
      </div>

      {isLiveAssembly ? (
        <p className="mt-2 text-[11px] font-medium text-[#1d4ed8]">Streaming assembly changes in real time...</p>
      ) : null}
    </section>
  );
}

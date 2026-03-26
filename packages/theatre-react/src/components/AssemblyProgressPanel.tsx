export interface AssemblyProgressEvent {
  event_id?: string;
  event_type?: string;
  title?: string;
  detail?: string;
  timestamp?: string;
}

export interface AssemblyProgressPanelProps {
  events: AssemblyProgressEvent[];
  activeEvent: AssemblyProgressEvent | null;
}

type AssemblyRow = {
  id: string;
  type: string;
  title: string;
  detail: string;
};

const EVT_ASSEMBLY_COMPLETED = "assembly_completed";
const EVT_ASSEMBLY_COMPLETE = "assembly_complete";
const EVT_ASSEMBLY_ERROR = "assembly_error";
const EVT_ASSEMBLY_STARTED = "assembly_started";
const EVT_ASSEMBLY_STEP_ADDED = "assembly_step_added";
const EVT_EXECUTION_STARTING = "execution_starting";

function toRows(events: AssemblyProgressEvent[]): AssemblyRow[] {
  const rows: AssemblyRow[] = [];
  for (const event of events) {
    const type = String(event.event_type || "").trim().toLowerCase();
    if (
      type !== EVT_ASSEMBLY_STARTED &&
      type !== EVT_ASSEMBLY_STEP_ADDED &&
      type !== EVT_ASSEMBLY_COMPLETE &&
      type !== EVT_ASSEMBLY_COMPLETED
    ) {
      continue;
    }
    rows.push({
      id: String(event.event_id || `${type}-${event.timestamp || ""}`),
      type,
      title: String(event.title || type.replace(/_/g, " ")).trim(),
      detail: String(event.detail || "").trim(),
    });
  }
  return rows;
}

function statusLabel(rows: AssemblyRow[]): string {
  const completed = rows.some((row) => row.type === EVT_ASSEMBLY_COMPLETE || row.type === EVT_ASSEMBLY_COMPLETED);
  return completed ? "Assembly complete" : "Assembling workflow";
}

function statusClass(rows: AssemblyRow[]): string {
  const completed = rows.some((row) => row.type === EVT_ASSEMBLY_COMPLETE || row.type === EVT_ASSEMBLY_COMPLETED);
  return completed ? "bg-[#ecfdf3] text-[#166534] border-[#bbf7d0]" : "bg-[#eff6ff] text-[#1d4ed8] border-[#bfdbfe]";
}

export function AssemblyProgressPanel({ events, activeEvent }: AssemblyProgressPanelProps) {
  const hasAssemblyError = events.some(
    (event) => String(event.event_type || "").trim().toLowerCase() === EVT_ASSEMBLY_ERROR,
  );
  const hasExecutionStarted = events.some(
    (event) => String(event.event_type || "").trim().toLowerCase() === EVT_EXECUTION_STARTING,
  );
  if (hasAssemblyError || hasExecutionStarted) {
    return null;
  }

  const rows = toRows(events);
  if (!rows.length) {
    return null;
  }

  const stepCount = rows.filter((row) => row.type === EVT_ASSEMBLY_STEP_ADDED).length;
  const latestNarration = String(rows[rows.length - 1]?.detail || rows[rows.length - 1]?.title || "").trim();
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
        {stepCount} step{stepCount === 1 ? "" : "s"} prepared.
      </p>
      {isLiveAssembly && latestNarration ? (
        <p className="mt-1.5 text-[11px] text-[#475467]">{latestNarration}</p>
      ) : null}
    </section>
  );
}

export interface BrainReviewEvent {
  event_id?: string;
  event_type?: string;
  title?: string;
  detail?: string;
  timestamp?: string;
  data?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
}

export interface BrainReviewPanelProps {
  events: BrainReviewEvent[];
}

type BrainReviewRow = {
  id: string;
  type: string;
  fromAgent: string;
  toAgent: string;
  title: string;
  detail: string;
  decision: string;
};

const BRAIN_EVENT_TYPES = new Set<string>([
  "brain_review_started",
  "brain_review_decision",
  "brain_revision_requested",
  "brain_question",
  "brain_answer_received",
]);

function readPayload(event: BrainReviewEvent): Record<string, unknown> {
  const data = event.data && typeof event.data === "object" ? event.data : {};
  const metadata = event.metadata && typeof event.metadata === "object" ? event.metadata : {};
  return { ...metadata, ...data };
}

function readRow(event: BrainReviewEvent): BrainReviewRow | null {
  const type = String(event.event_type || "").trim().toLowerCase();
  if (!BRAIN_EVENT_TYPES.has(type)) {
    return null;
  }
  const data = readPayload(event);
  const fromAgent = String(data.from_agent || "brain").trim() || "brain";
  const toAgent = String(data.to_agent || data.agent_id || "agent").trim() || "agent";
  const decision = String(data.decision || "").trim().toLowerCase();
  return {
    id: String(event.event_id || `${type}-${event.timestamp || ""}`),
    type,
    fromAgent,
    toAgent,
    title: String(event.title || "Brain review").trim() || "Brain review",
    detail: String(event.detail || data.reasoning || data.feedback || data.question || data.answer || "").trim(),
    decision,
  };
}

function decisionBadgeClass(row: BrainReviewRow): string {
  if (row.decision === "proceed") return "bg-[#ecfdf3] text-[#166534] border-[#a7f3d0]";
  if (row.decision === "revise" || row.type === "brain_revision_requested") {
    return "bg-[#fff7ed] text-[#9a3412] border-[#fed7aa]";
  }
  if (row.decision === "question" || row.type === "brain_question" || row.type === "brain_answer_received") {
    return "bg-[#eff6ff] text-[#1d4ed8] border-[#bfdbfe]";
  }
  if (row.decision === "escalate") return "bg-[#fef2f2] text-[#991b1b] border-[#fecaca]";
  return "bg-[#f8fafc] text-[#475467] border-[#e4e7ec]";
}

function decisionLabel(row: BrainReviewRow): string {
  if (row.decision) return row.decision;
  if (row.type === "brain_review_started") return "started";
  if (row.type === "brain_revision_requested") return "revise";
  if (row.type === "brain_question") return "question";
  if (row.type === "brain_answer_received") return "answer";
  return "review";
}

export function BrainReviewPanel({ events }: BrainReviewPanelProps) {
  const rows = events
    .map((event) => readRow(event))
    .filter((row): row is BrainReviewRow => Boolean(row))
    .slice(-4);

  if (!rows.length) {
    return null;
  }

  return (
    <section className="mt-3 rounded-2xl border border-[#e0e7ff] bg-[linear-gradient(180deg,#eef2ff_0%,#f8faff_100%)] px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#4338ca]">Brain review</p>
      <div className="mt-2 space-y-2">
        {rows.map((row) => (
          <article key={row.id} className="rounded-xl border border-[#dbeafe] bg-white px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-[#eef2ff] px-2 py-0.5 text-[10px] font-semibold text-[#3730a3]">
                {row.fromAgent}
              </span>
              <span className="text-[10px] text-[#98a2b3]">-&gt;</span>
              <span className="rounded-full bg-[#eef2ff] px-2 py-0.5 text-[10px] font-semibold text-[#3730a3]">
                {row.toAgent}
              </span>
              <span className={`ml-auto rounded-full border px-2 py-0.5 text-[10px] font-semibold ${decisionBadgeClass(row)}`}>
                {decisionLabel(row)}
              </span>
            </div>
            <p className="mt-1 text-[12px] font-medium text-[#111827]">{row.title}</p>
            {row.detail ? <p className="mt-0.5 text-[11px] leading-[1.45] text-[#475467]">{row.detail}</p> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

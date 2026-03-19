import type { AgentActivityEvent } from "../../types";

type AgentHandoffRelayProps = {
  event: AgentActivityEvent | null;
};

function readHandoff(event: AgentActivityEvent | null): {
  fromAgent: string;
  toAgent: string;
  summary: string;
} | null {
  if (!event) {
    return null;
  }
  const type = String(event.event_type || "").trim().toLowerCase();
  if (type !== "agent_handoff" && type !== "agent.handoff") {
    return null;
  }
  const data = ((event.data ?? event.metadata) ?? {}) as Record<string, unknown>;
  const fromAgent = String(
    data.from_agent || data.source_agent || data.from || event.title.split("→")[0] || "Researcher",
  ).trim();
  const toAgent = String(
    data.to_agent || data.target_agent || data.to || event.title.split("→")[1] || "Analyst",
  ).trim();
  const summary = String(
    data.summary || data.message || data.handoff_instruction || event.detail || "Passing context to next specialist.",
  ).trim();
  return {
    fromAgent: fromAgent || "Researcher",
    toAgent: toAgent || "Analyst",
    summary,
  };
}

export function AgentHandoffRelay({ event }: AgentHandoffRelayProps) {
  const handoff = readHandoff(event);
  if (!handoff) {
    return null;
  }

  return (
    <section className="mt-3 rounded-2xl border border-[#dbeafe] bg-[linear-gradient(180deg,#eff6ff_0%,#f8fbff_100%)] px-4 py-3">
      <style>{`
        @keyframes handoff-baton {
          0% { left: 0%; opacity: 0.65; }
          50% { opacity: 1; }
          100% { left: calc(100% - 14px); opacity: 0.75; }
        }
      `}</style>
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#1d4ed8]">
        Agent handoff
      </p>
      <div className="mt-1 flex items-center gap-2 text-[14px] font-semibold text-[#1e3a8a]">
        <span>{handoff.fromAgent}</span>
        <span className="text-[#60a5fa]">→</span>
        <span>{handoff.toAgent}</span>
      </div>
      <div className="relative mt-2 h-2 rounded-full bg-[#dbeafe]">
        <span
          className="absolute top-[-3px] h-[14px] w-[14px] rounded-full bg-[#2563eb] shadow-[0_0_0_3px_rgba(37,99,235,0.2)]"
          style={{ animation: "handoff-baton 1.15s ease-in-out infinite alternate" }}
        />
      </div>
      <p className="mt-2 text-[12px] text-[#334155]">{handoff.summary}</p>
    </section>
  );
}

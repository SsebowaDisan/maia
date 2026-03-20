import type { AgentActivityEvent } from "../../types";
import { readEventPayload } from "../../utils/eventPayload";
import {
  EVT_AGENT_DIALOGUE_RESOLVED,
  EVT_AGENT_DIALOGUE_STARTED,
} from "../../constants/eventTypes";

type AgentHandoffRelayProps = {
  event: AgentActivityEvent | null;
};

type RelayPayload = {
  kind: "handoff" | "dialogue";
  label: string;
  fromAgent: string;
  toAgent: string;
  summary: string;
};

function readRelay(event: AgentActivityEvent | null): RelayPayload | null {
  if (!event) {
    return null;
  }
  const type = String(event.event_type || "").trim().toLowerCase();
  const isHandoff = type === "agent_handoff" || type === "agent.handoff";
  const isDialogue = type === EVT_AGENT_DIALOGUE_STARTED || type === EVT_AGENT_DIALOGUE_RESOLVED;
  if (!isHandoff && !isDialogue) {
    return null;
  }

  const data = readEventPayload(event);
  const title = String(event.title || "").trim();
  const [left = "", right = ""] = title.split(/->|→/).map((part) => part.trim());
  const fromAgent = String(data.from_agent || data.source_agent || data.from || left || "Researcher").trim();
  const toAgent = String(data.to_agent || data.target_agent || data.to || right || "Analyst").trim();
  const summary = String(
    data.summary || data.message || data.handoff_instruction || event.detail || "Passing context to next specialist.",
  ).trim();
  return {
    kind: isDialogue ? "dialogue" : "handoff",
    label: isDialogue ? "Agent dialogue" : "Agent handoff",
    fromAgent: fromAgent || "Researcher",
    toAgent: toAgent || "Analyst",
    summary,
  };
}

function sectionClasses(kind: RelayPayload["kind"]) {
  if (kind === "dialogue") {
    return {
      section: "mt-3 rounded-2xl border border-[#a7f3d0] bg-[linear-gradient(180deg,#ecfdf5_0%,#f0fdf4_100%)] px-4 py-3",
      label: "text-[11px] font-semibold uppercase tracking-[0.08em] text-[#047857]",
      flow: "mt-1 flex items-center gap-2 text-[14px] font-semibold text-[#065f46]",
      track: "relative mt-2 h-2 rounded-full bg-[#bbf7d0]",
      dot: "absolute top-[-3px] h-[14px] w-[14px] rounded-full bg-[#059669] shadow-[0_0_0_3px_rgba(5,150,105,0.2)]",
      summary: "mt-2 text-[12px] text-[#065f46]",
    };
  }
  return {
    section: "mt-3 rounded-2xl border border-[#dbeafe] bg-[linear-gradient(180deg,#eff6ff_0%,#f8fbff_100%)] px-4 py-3",
    label: "text-[11px] font-semibold uppercase tracking-[0.08em] text-[#1d4ed8]",
    flow: "mt-1 flex items-center gap-2 text-[14px] font-semibold text-[#1e3a8a]",
    track: "relative mt-2 h-2 rounded-full bg-[#dbeafe]",
    dot: "absolute top-[-3px] h-[14px] w-[14px] rounded-full bg-[#2563eb] shadow-[0_0_0_3px_rgba(37,99,235,0.2)]",
    summary: "mt-2 text-[12px] text-[#334155]",
  };
}

export function AgentHandoffRelay({ event }: AgentHandoffRelayProps) {
  const relay = readRelay(event);
  if (!relay) {
    return null;
  }
  const classes = sectionClasses(relay.kind);

  return (
    <section className={classes.section}>
      <style>{`
        @keyframes handoff-baton {
          0% { left: 0%; opacity: 0.65; }
          50% { opacity: 1; }
          100% { left: calc(100% - 14px); opacity: 0.75; }
        }
      `}</style>
      <p className={classes.label}>{relay.label}</p>
      <div className={classes.flow}>
        <span>{relay.fromAgent}</span>
        <span className="text-[#60a5fa]">-&gt;</span>
        <span>{relay.toAgent}</span>
      </div>
      <div className={classes.track}>
        <span
          className={classes.dot}
          style={{ animation: "handoff-baton 1.15s ease-in-out infinite alternate" }}
        />
      </div>
      <p className={classes.summary}>{relay.summary}</p>
    </section>
  );
}

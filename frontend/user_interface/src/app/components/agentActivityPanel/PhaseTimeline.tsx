import type { ActivityPhaseRow } from "./helpers";

interface PhaseTimelineProps {
  phases: ActivityPhaseRow[];
  streaming: boolean;
}

const phaseStateClass: Record<ActivityPhaseRow["state"], string> = {
  pending: "border-black/[0.08] bg-white/70 text-[#8d8d92]",
  active: "border-[#1d1d1f]/25 bg-[#1d1d1f] text-white",
  completed: "border-[#1d1d1f]/18 bg-[#f0f1f4] text-[#1d1d1f]",
};

function PhaseTimeline({ phases, streaming }: PhaseTimelineProps) {
  if (!phases.length) {
    return null;
  }

  return (
    <div className="mb-3 rounded-2xl border border-black/[0.06] bg-white/85 px-3 py-2">
      <div className="mb-1 flex items-center justify-between gap-2">
        <p className="text-[11px] uppercase tracking-[0.1em] text-[#6e6e73]">
          Execution Phases
        </p>
        <span className="text-[10px] text-[#86868b]">
          {streaming ? "Live phase stream" : "Replay phase history"}
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {phases.map((phase) => (
          <span
            key={`phase-${phase.key}`}
            className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.07em] ${phaseStateClass[phase.state]}`}
            title={phase.latestEventTitle || `${phase.label} phase`}
          >
            <span>{phase.label}</span>
            <span className="opacity-80">
              {phase.state === "active" ? "Live" : phase.state === "completed" ? "Done" : "Pending"}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

export { PhaseTimeline };

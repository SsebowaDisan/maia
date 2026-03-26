export interface ActivityPhaseRow {
  key: string;
  label: string;
  state: "pending" | "active" | "completed" | string;
  latestEventTitle?: string;
}

export interface PhaseTimelineProps {
  phases: ActivityPhaseRow[];
  streaming: boolean;
  eventCount?: number;
}

const phaseStateClass: Record<string, string> = {
  pending: "border-black/[0.08] bg-white/70 text-[#8d8d92]",
  active: "border-[#1d1d1f]/25 bg-[#1d1d1f] text-white",
  completed: "border-[#1d1d1f]/18 bg-[#f0f1f4] text-[#1d1d1f]",
};

const phaseDotClass: Record<string, string> = {
  pending: "bg-black/15",
  active: "animate-pulse bg-white",
  completed: "bg-[#34c759]",
};

export function PhaseTimeline({ phases, streaming, eventCount }: PhaseTimelineProps) {
  if (!phases.length) {
    return null;
  }

  return (
    <div className="mb-3 rounded-2xl border border-black/[0.06] bg-white/85 px-3 py-2">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-[11px] tracking-[0.04em] text-[#6e6e73]">How Maia is working</p>
        {eventCount != null && eventCount > 0 && streaming ? (
          <span className="inline-flex items-center gap-1 text-[10px] text-[#86868b]">
            <span className="h-1 w-1 animate-pulse rounded-full bg-[#34c759]" />
            <span>Live now</span>
          </span>
        ) : null}
      </div>

      <div className="relative flex flex-wrap items-center gap-x-0 gap-y-1.5">
        {phases.map((phase, i) => (
          <div key={`phase-${phase.key}`} className="inline-flex items-center">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold tracking-[0.04em] ${phaseStateClass[phase.state] ?? phaseStateClass.pending}`}
              title={phase.latestEventTitle || phase.label}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${phaseDotClass[phase.state] ?? phaseDotClass.pending}`} />
              <span>{phase.label}</span>
            </span>
            {i < phases.length - 1 ? (
              <span
                className={`mx-1 h-px w-4 shrink-0 rounded-full transition-colors duration-500 ${
                  phase.state === "completed" ? "bg-[#1d1d1f]/30" : "bg-black/[0.07]"
                }`}
              />
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

import { useMemo } from "react";

import type { AgentActivityEvent } from "../types";

type LeftExecutionRailProps = {
  activityEvents: AgentActivityEvent[];
  pendingSteps: string[];
};

function cleanText(value: unknown): string {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function resolveActiveAgentLabel(activityEvents: AgentActivityEvent[]): string {
  for (let index = activityEvents.length - 1; index >= 0; index -= 1) {
    const event = activityEvents[index];
    const data = event.data && typeof event.data === "object" ? (event.data as Record<string, unknown>) : {};
    const label = cleanText(data.agent_label || data.agent_role || data.owner_role);
    if (label) {
      return label;
    }
  }
  return "system";
}

function LeftExecutionRail({ activityEvents, pendingSteps }: LeftExecutionRailProps) {
  const activeAgentLabel = useMemo(
    () => resolveActiveAgentLabel(activityEvents),
    [activityEvents],
  );
  const visiblePendingSteps = useMemo(() => {
    const rows = pendingSteps.map((step) => cleanText(step)).filter((step) => step.length > 0);
    return rows.slice(0, 4);
  }, [pendingSteps]);

  return (
    <aside className="hidden w-[210px] shrink-0 border-r border-black/[0.06] bg-gradient-to-b from-white to-[#f7f7f9] px-3 py-4 xl:block">
      <div className="rounded-xl border border-black/[0.08] bg-white p-3 shadow-sm">
        <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Active agent</p>
        <p className="mt-1 text-[13px] font-semibold text-[#1d1d1f]">{activeAgentLabel}</p>
        <p className="mt-1 text-[11px] text-[#6e6e73]">
          Live ownership inferred from current execution events.
        </p>
      </div>

      <div className="mt-3 rounded-xl border border-black/[0.08] bg-white p-3 shadow-sm">
        <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Pending tasks</p>
        {visiblePendingSteps.length > 0 ? (
          <ol className="mt-2 space-y-1.5 text-[11px] text-[#1d1d1f]">
            {visiblePendingSteps.map((step, index) => (
              <li key={`${index}-${step}`} className="rounded-lg border border-black/[0.06] bg-[#fafafc] px-2 py-1.5">
                {step}
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-2 text-[11px] text-[#6e6e73]">No pending tasks queued.</p>
        )}
      </div>
    </aside>
  );
}

export { LeftExecutionRail };

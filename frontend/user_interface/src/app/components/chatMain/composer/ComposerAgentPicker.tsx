import { useMemo } from "react";

import { AGENT_OS_AGENTS } from "../../../pages/agentOsData";

type ComposerAgentPickerProps = {
  query: string;
  onPick: (agentName: string) => void;
};

export function ComposerAgentPicker({ query, onPick }: ComposerAgentPickerProps) {
  const normalizedQuery = query.trim().toLowerCase().replace(/^@+/, "");
  const options = useMemo(
    () =>
      AGENT_OS_AGENTS.filter((agent) =>
        !normalizedQuery
          ? true
          : `${agent.name} ${agent.description}`.toLowerCase().includes(normalizedQuery),
      ),
    [normalizedQuery],
  );

  return (
    <div className="absolute left-3 top-[60px] z-30 w-[420px] rounded-2xl border border-black/[0.12] bg-white p-2 shadow-[0_20px_36px_rgba(15,23,42,0.18)]">
      <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Agents</p>
      <div className="space-y-1">
        {options.map((agent) => (
          <button
            key={agent.id}
            type="button"
            onClick={() => onPick(agent.name)}
            className="w-full rounded-xl px-2 py-2 text-left hover:bg-[#f8fafc]"
          >
            <p className="text-[13px] font-semibold text-[#111827]">{agent.name}</p>
            <p className="text-[12px] text-[#667085]">{agent.description}</p>
          </button>
        ))}
        {!options.length ? (
          <a
            href="/marketplace"
            className="block rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-[12px] font-semibold text-[#344054]"
          >
            No installed match. Browse marketplace
          </a>
        ) : null}
      </div>
    </div>
  );
}


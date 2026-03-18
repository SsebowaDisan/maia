type ConnectorAgentAccessListProps = {
  connectorId: string;
  agents: Array<{
    id: string;
    name: string;
  }>;
  allowedAgentIds: string[];
  disabled?: boolean;
  onChange: (allowedAgentIds: string[]) => void;
};

function toggleValue(values: string[], nextValue: string): string[] {
  if (values.includes(nextValue)) {
    return values.filter((value) => value !== nextValue);
  }
  return [...values, nextValue];
}

export function ConnectorAgentAccessList({
  connectorId,
  agents,
  allowedAgentIds,
  disabled = false,
  onChange,
}: ConnectorAgentAccessListProps) {
  return (
    <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="mb-3">
        <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
          Agent access
        </p>
        <p className="mt-1 text-[13px] text-[#667085]">
          Control which agents can use the `{connectorId}` binding in this workspace.
        </p>
      </div>

      <div className="space-y-2">
        {agents.map((agent) => {
          const checked = allowedAgentIds.includes(agent.id);
          return (
            <label
              key={agent.id}
              className="flex items-center justify-between gap-3 rounded-xl border border-black/[0.06] px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate text-[13px] font-medium text-[#111827]">{agent.name}</p>
                <p className="text-[11px] text-[#667085]">{agent.id}</p>
              </div>
              <span className="inline-flex items-center gap-2 text-[12px] text-[#344054]">
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={disabled}
                  onChange={() => onChange(toggleValue(allowedAgentIds, agent.id))}
                  className="h-4 w-4 rounded border border-black/[0.25]"
                />
                {checked ? "Allowed" : "Blocked"}
              </span>
            </label>
          );
        })}
      </div>
    </section>
  );
}

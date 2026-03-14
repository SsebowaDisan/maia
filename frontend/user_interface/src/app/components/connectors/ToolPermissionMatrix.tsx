import type { AgentSummary, ConnectorSummary } from "../../pages/agentOsData";

export type ToolPermissionMatrixProps = {
  agents: AgentSummary[];
  connectors: ConnectorSummary[];
  value: Record<string, string[]>;
  onChange: (next: Record<string, string[]>) => void;
};

function isChecked(matrix: Record<string, string[]>, connectorId: string, agentId: string): boolean {
  const allowed = matrix[connectorId] || [];
  return allowed.includes(agentId);
}

function togglePermission(
  matrix: Record<string, string[]>,
  connectorId: string,
  agentId: string,
): Record<string, string[]> {
  const current = matrix[connectorId] || [];
  if (current.includes(agentId)) {
    return {
      ...matrix,
      [connectorId]: current.filter((id) => id !== agentId),
    };
  }
  return {
    ...matrix,
    [connectorId]: [...current, agentId],
  };
}

export function ToolPermissionMatrix({
  agents,
  connectors,
  value,
  onChange,
}: ToolPermissionMatrixProps) {
  return (
    <div className="overflow-x-auto rounded-[20px] border border-black/[0.08] bg-white">
      <table className="min-w-full border-collapse text-left text-[13px]">
        <thead>
          <tr className="bg-[#f8fafc] text-[#475467]">
            <th className="border-b border-black/[0.06] px-4 py-3 font-semibold">Connector</th>
            {agents.map((agent) => (
              <th
                key={agent.id}
                className="border-b border-black/[0.06] px-4 py-3 font-semibold whitespace-nowrap"
              >
                {agent.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {connectors.map((connector) => (
            <tr key={connector.id} className="border-b border-black/[0.05] last:border-b-0">
              <td className="px-4 py-3">
                <p className="font-semibold text-[#111827]">{connector.name}</p>
                <p className="text-[12px] text-[#667085]">{connector.id}</p>
              </td>
              {agents.map((agent) => {
                const checked = isChecked(value, connector.id, agent.id);
                return (
                  <td key={`${connector.id}-${agent.id}`} className="px-4 py-3">
                    <label className="inline-flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => onChange(togglePermission(value, connector.id, agent.id))}
                        className="h-4 w-4 rounded border border-black/[0.25]"
                      />
                      <span className="text-[12px] text-[#344054]">
                        {checked ? "Allowed" : "Blocked"}
                      </span>
                    </label>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


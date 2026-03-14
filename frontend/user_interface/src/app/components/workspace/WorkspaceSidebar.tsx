type WorkspaceSidebarConnector = {
  id: string;
  name: string;
  authType: string;
  status: "Connected" | "Not connected" | "Expired";
};

type WorkspaceSidebarAgent = {
  id: string;
  status: "active" | "paused" | "error";
};

type WorkspaceSidebarProps = {
  connectors: WorkspaceSidebarConnector[];
  agents: WorkspaceSidebarAgent[];
  onOpenConnector?: (connectorId: string) => void;
};

function statusDotClass(status: WorkspaceSidebarConnector["status"]): string {
  if (status === "Connected") {
    return "bg-[#16a34a]";
  }
  if (status === "Expired") {
    return "bg-[#d97706]";
  }
  return "bg-[#98a2b3]";
}

export function WorkspaceSidebar({
  connectors,
  agents,
  onOpenConnector,
}: WorkspaceSidebarProps) {
  const activeAgents = agents.filter((agent) => agent.status === "active").length;
  return (
    <aside className="h-full w-[280px] shrink-0 rounded-[24px] border border-black/[0.08] bg-white p-4 shadow-[0_14px_34px_rgba(15,23,42,0.08)]">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#667085]">Workspace</p>
      <h2 className="mt-1 text-[20px] font-semibold tracking-[-0.02em] text-[#101828]">Operations Rail</h2>

      <div className="mt-4 rounded-2xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2">
        <p className="text-[12px] text-[#667085]">Active agents</p>
        <p className="text-[26px] font-semibold tracking-[-0.02em] text-[#111827]">{activeAgents}</p>
      </div>

      <div className="mt-4 space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Connected services</p>
        {connectors.map((connector) => (
          <button
            key={connector.id}
            type="button"
            onClick={() => onOpenConnector?.(connector.id)}
            className="flex w-full items-center justify-between rounded-xl border border-black/[0.06] bg-white px-3 py-2 text-left hover:border-black/[0.14]"
          >
            <div>
              <p className="text-[13px] font-semibold text-[#111827]">{connector.name}</p>
              <p className="text-[11px] text-[#667085]">{connector.authType}</p>
            </div>
            <span className={`h-2.5 w-2.5 rounded-full ${statusDotClass(connector.status)}`} />
          </button>
        ))}
      </div>
    </aside>
  );
}

import { useMemo } from "react";

import { AGENT_OS_CONNECTORS, AGENT_OS_MARKETPLACE } from "./agentOsData";

type MarketplaceAgentDetailPageProps = {
  agentId: string;
};

export function MarketplaceAgentDetailPage({ agentId }: MarketplaceAgentDetailPageProps) {
  const agent = useMemo(
    () => AGENT_OS_MARKETPLACE.find((item) => item.id === agentId) || null,
    [agentId],
  );

  if (!agent) {
    return (
      <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
        <div className="mx-auto max-w-[980px] rounded-2xl border border-black/[0.08] bg-white p-5">
          <h1 className="text-[24px] font-semibold text-[#101828]">Agent not found</h1>
          <a href="/marketplace" className="mt-3 inline-block text-[13px] font-semibold text-[#1d4ed8] hover:underline">
            Back to marketplace
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1080px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_54px_rgba(15,23,42,0.1)]">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Marketplace agent</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">{agent.name}</h1>
          <p className="mt-2 text-[15px] text-[#475467]">{agent.description}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#344054]">
              ⭐ {agent.rating.toFixed(1)}
            </span>
            <span className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#344054]">
              {agent.installs.toLocaleString()} installs
            </span>
            <span className="rounded-full border border-[#d0d5dd] bg-white px-2.5 py-1 text-[11px] font-semibold uppercase text-[#344054]">
              {agent.pricing}
            </span>
          </div>
        </section>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <h2 className="text-[18px] font-semibold text-[#111827]">Required connectors</h2>
            <div className="mt-3 space-y-2">
              {agent.requiredConnectors.map((required) => {
                const connected = AGENT_OS_CONNECTORS.some((connector) => connector.id.includes(required) && connector.status === "Connected");
                return (
                  <div key={required} className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] px-3 py-2">
                    <p className="text-[13px] font-semibold text-[#111827]">{required}</p>
                    <p className={`text-[12px] ${connected ? "text-[#166534]" : "text-[#b42318]"}`}>
                      {connected ? "Connected in tenant" : "Not connected yet"}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <h2 className="text-[18px] font-semibold text-[#111827]">Changelog</h2>
            <ul className="mt-3 list-disc space-y-1 pl-4 text-[13px] text-[#475467]">
              {agent.versions.map((version) => (
                <li key={version}>Version {version}</li>
              ))}
            </ul>
          </div>
        </section>

        <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
          <h2 className="text-[18px] font-semibold text-[#111827]">Reviews</h2>
          <div className="mt-3 space-y-2">
            <div className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3">
              <p className="text-[13px] font-semibold text-[#111827]">Great quality and clean outputs</p>
              <p className="mt-1 text-[12px] text-[#667085]">"The weekly summaries reduced manual reporting work by 60%."</p>
            </div>
            <div className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3">
              <p className="text-[13px] font-semibold text-[#111827]">Needs broader connector defaults</p>
              <p className="mt-1 text-[12px] text-[#667085]">"Strong core logic, but we had to map several internal tools manually."</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}


import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { toast } from "sonner";

import { AgentInstallModal } from "../components/marketplace/AgentInstallModal";
import { AGENT_OS_MARKETPLACE } from "./agentOsData";

export function MarketplacePage() {
  const [query, setQuery] = useState("");
  const [pricingFilter, setPricingFilter] = useState<"all" | "free" | "paid" | "enterprise">("all");
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [installedAgentIds, setInstalledAgentIds] = useState<string[]>([]);

  const filteredAgents = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return AGENT_OS_MARKETPLACE.filter((agent) => {
      if (pricingFilter !== "all" && agent.pricing !== pricingFilter) {
        return false;
      }
      if (!normalizedQuery) {
        return true;
      }
      return (
        agent.name.toLowerCase().includes(normalizedQuery) ||
        agent.description.toLowerCase().includes(normalizedQuery) ||
        agent.tags.some((tag) => tag.toLowerCase().includes(normalizedQuery))
      );
    });
  }, [pricingFilter, query]);

  const selectedAgent = AGENT_OS_MARKETPLACE.find((agent) => agent.id === selectedAgentId) || null;

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1320px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_54px_rgba(15,23,42,0.1)]">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Marketplace</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Install production-ready agents</h1>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <label className="relative min-w-[280px]">
              <Search className="pointer-events-none absolute left-3 top-2.5 text-[#98a2b3]" size={15} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search by name, tag, or description"
                className="w-full rounded-full border border-black/[0.12] bg-white py-2 pl-9 pr-3 text-[13px]"
              />
            </label>
            {(["all", "free", "paid", "enterprise"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setPricingFilter(value)}
                className={`rounded-full px-3 py-1.5 text-[12px] font-semibold capitalize ${
                  pricingFilter === value ? "bg-[#111827] text-white" : "border border-black/[0.12] bg-white text-[#344054]"
                }`}
              >
                {value}
              </button>
            ))}
          </div>
        </section>

        <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filteredAgents.map((agent) => {
            const installed = installedAgentIds.includes(agent.id);
            return (
              <article
                key={agent.id}
                className="rounded-[22px] border border-black/[0.08] bg-white p-5 shadow-[0_14px_36px_rgba(15,23,42,0.08)]"
              >
                <p className="text-[12px] text-[#667085]">{agent.publisher}</p>
                <h2 className="mt-1 text-[18px] font-semibold text-[#111827]">{agent.name}</h2>
                <p className="mt-2 text-[13px] leading-[1.5] text-[#475467]">{agent.description}</p>
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
                <div className="mt-4 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setSelectedAgentId(agent.id)}
                    className={`rounded-full px-4 py-2 text-[12px] font-semibold ${
                      installed
                        ? "border border-[#bbf7d0] bg-[#ecfdf3] text-[#166534]"
                        : "bg-[#111827] text-white"
                    }`}
                  >
                    {installed ? "Installed" : "Install"}
                  </button>
                  <a
                    href={`/marketplace/agents/${encodeURIComponent(agent.id)}`}
                    className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054]"
                  >
                    View detail
                  </a>
                </div>
              </article>
            );
          })}
        </section>
      </div>

      <AgentInstallModal
        open={Boolean(selectedAgent)}
        agent={selectedAgent}
        onClose={() => setSelectedAgentId(null)}
        onInstall={(agentId) => {
          setInstalledAgentIds((previous) => (previous.includes(agentId) ? previous : [...previous, agentId]));
          setSelectedAgentId(null);
          toast.success("Agent installed. Open workspace to configure runtime settings.");
        }}
      />
    </div>
  );
}


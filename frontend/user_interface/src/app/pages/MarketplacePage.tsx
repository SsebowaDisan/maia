import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { toast } from "sonner";

import {
  listAgents,
  installMarketplaceAgent,
  listConnectorCatalog,
  listMarketplaceAgents,
  getMarketplaceAgent,
  type MarketplaceAgentDetail,
  type MarketplaceAgentSummary,
} from "../../api/client";
import { AgentInstallModal } from "../components/marketplace/AgentInstallModal";

type PricingFilter = "all" | "free" | "paid" | "enterprise";

function navigateToPath(path: string) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function MarketplacePage() {
  const [query, setQuery] = useState("");
  const [pricingFilter, setPricingFilter] = useState<PricingFilter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [agents, setAgents] = useState<MarketplaceAgentSummary[]>([]);
  const [availableConnectorIds, setAvailableConnectorIds] = useState<string[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedAgentDetail, setSelectedAgentDetail] = useState<MarketplaceAgentDetail | null>(null);
  const [installing, setInstalling] = useState(false);
  const [installedAgentIds, setInstalledAgentIds] = useState<string[]>([]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [rows, connectors, installedAgents] = await Promise.all([
          listMarketplaceAgents({
            q: query.trim() || undefined,
            pricing: pricingFilter === "all" ? undefined : pricingFilter,
            sort_by: "installs",
            limit: 60,
          }),
          listConnectorCatalog(),
          listAgents(),
        ]);
        setAgents(rows || []);
        setAvailableConnectorIds((connectors || []).map((row) => row.id).filter(Boolean));
        setInstalledAgentIds(
          (installedAgents || [])
            .map((agent) => String(agent.agent_id || "").trim())
            .filter(Boolean),
        );
      } catch (nextError) {
        const message = String(nextError || "Failed to load marketplace.");
        setError(message);
      } finally {
        setLoading(false);
      }
    };
    const timer = window.setTimeout(() => {
      void load();
    }, 250);
    return () => window.clearTimeout(timer);
  }, [pricingFilter, query]);

  useEffect(() => {
    if (!selectedAgentId) {
      setSelectedAgentDetail(null);
      return;
    }
    const loadDetail = async () => {
      try {
        const detail = await getMarketplaceAgent(selectedAgentId);
        setSelectedAgentDetail(detail);
      } catch (nextError) {
        toast.error(`Unable to load install details: ${String(nextError)}`);
        setSelectedAgentId(null);
      }
    };
    void loadDetail();
  }, [selectedAgentId]);

  const filteredAgents = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return agents.filter((agent) => {
      if (pricingFilter !== "all" && agent.pricing_tier !== pricingFilter) {
        return false;
      }
      if (!normalizedQuery) {
        return true;
      }
      return (
        agent.name.toLowerCase().includes(normalizedQuery) ||
        agent.description.toLowerCase().includes(normalizedQuery) ||
        (agent.tags || []).some((tag) => tag.toLowerCase().includes(normalizedQuery))
      );
    });
  }, [agents, pricingFilter, query]);

  const installSelectedAgent = async (
    agentId: string,
    payload: { version?: string | null; connector_mapping: Record<string, string> },
  ) => {
    setInstalling(true);
    try {
      const result = await installMarketplaceAgent(agentId, payload);
      if (!result.success) {
        if (result.missing_connectors?.length) {
          toast.error(`Missing connectors: ${result.missing_connectors.join(", ")}`);
        } else {
          toast.error(result.error || "Install failed.");
        }
        return;
      }
      setInstalledAgentIds((previous) =>
        previous.includes(agentId) ? previous : [...previous, agentId],
      );
      setSelectedAgentId(null);
      setSelectedAgentDetail(null);
      toast.success("Agent installed. Redirecting to workspace...");
      navigateToPath("/workspace");
    } catch (nextError) {
      toast.error(`Install failed: ${String(nextError)}`);
    } finally {
      setInstalling(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1320px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_54px_rgba(15,23,42,0.1)]">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Marketplace</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">
            Install production-ready agents
          </h1>
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
                  pricingFilter === value
                    ? "bg-[#111827] text-white"
                    : "border border-black/[0.12] bg-white text-[#344054]"
                }`}
              >
                {value}
              </button>
            ))}
          </div>
        </section>

        {error ? (
          <section className="rounded-2xl border border-[#fca5a5] bg-[#fff1f2] p-4 text-[13px] text-[#9f1239]">
            {error}
          </section>
        ) : null}

        {loading ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-6 text-[14px] text-[#667085]">
            Loading marketplace agents...
          </section>
        ) : (
          <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {filteredAgents.map((agent) => {
              const installed = installedAgentIds.includes(agent.agent_id);
              return (
                <article
                  key={agent.id}
                  className="rounded-[22px] border border-black/[0.08] bg-white p-5 shadow-[0_14px_36px_rgba(15,23,42,0.08)]"
                >
                  <p className="text-[12px] text-[#667085]">
                    {agent.verified ? "Verified publisher" : "Community publisher"}
                  </p>
                  <h2 className="mt-1 text-[18px] font-semibold text-[#111827]">{agent.name}</h2>
                  <p className="mt-2 text-[13px] leading-[1.5] text-[#475467]">{agent.description}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#344054]">
                      {Number(agent.avg_rating || 0).toFixed(1)} rating
                    </span>
                    <span className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#344054]">
                      {(agent.install_count || 0).toLocaleString()} installs
                    </span>
                    <span className="rounded-full border border-[#d0d5dd] bg-white px-2.5 py-1 text-[11px] font-semibold uppercase text-[#344054]">
                      {agent.pricing_tier}
                    </span>
                  </div>
                  <div className="mt-4 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedAgentId(agent.agent_id)}
                      className={`rounded-full px-4 py-2 text-[12px] font-semibold ${
                        installed
                          ? "border border-[#bbf7d0] bg-[#ecfdf3] text-[#166534]"
                          : "bg-[#111827] text-white"
                      }`}
                    >
                      {installed ? "Installed" : "Install"}
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        navigateToPath(`/marketplace/agents/${encodeURIComponent(agent.agent_id)}`)
                      }
                      className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054]"
                    >
                      View detail
                    </button>
                  </div>
                </article>
              );
            })}
          </section>
        )}
      </div>

      <AgentInstallModal
        open={Boolean(selectedAgentDetail)}
        agent={selectedAgentDetail}
        availableConnectorIds={availableConnectorIds}
        installing={installing}
        onClose={() => {
          if (installing) {
            return;
          }
          setSelectedAgentId(null);
          setSelectedAgentDetail(null);
        }}
        onInstall={installSelectedAgent}
      />
    </div>
  );
}

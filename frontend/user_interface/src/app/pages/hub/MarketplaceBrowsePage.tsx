import { useEffect, useMemo, useState } from "react";

import {
  listMarketplaceAgents,
  listMarketplaceWorkflows,
  type MarketplaceAgentSummary,
  type MarketplaceWorkflowRecord,
} from "../../../api/client";
import { ConnectorBrandIcon } from "../../components/connectors/ConnectorBrandIcon";

type MarketplaceBrowsePageProps = {
  onNavigate: (path: string) => void;
};

type HubSortValue = "trending" | "newest" | "popular";

const CATEGORY_TABS = ["all", "analytics", "content", "data", "crm", "support", "automation"];

function readInitialSearchFromUrl(): string {
  const params = new URLSearchParams(window.location.search || "");
  return String(params.get("q") || "").trim();
}

function readInitialCategoryFromUrl(): string {
  const params = new URLSearchParams(window.location.search || "");
  const value = String(params.get("category") || "all").trim().toLowerCase();
  return CATEGORY_TABS.includes(value) ? value : "all";
}

function readInitialSortFromUrl(): HubSortValue {
  const params = new URLSearchParams(window.location.search || "");
  const value = String(params.get("sort") || "trending").trim().toLowerCase();
  if (value === "newest" || value === "popular") {
    return value;
  }
  return "trending";
}

function compactNumber(value: number): string {
  const amount = Number(value || 0);
  if (amount >= 1000000) {
    return `${(amount / 1000000).toFixed(1)}M`;
  }
  if (amount >= 1000) {
    return `${(amount / 1000).toFixed(1)}K`;
  }
  return String(amount);
}

export function MarketplaceBrowsePage({ onNavigate }: MarketplaceBrowsePageProps) {
  const [searchValue, setSearchValue] = useState(() => readInitialSearchFromUrl());
  const [category, setCategory] = useState(() => readInitialCategoryFromUrl());
  const [sortBy, setSortBy] = useState<HubSortValue>(() => readInitialSortFromUrl());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [agents, setAgents] = useState<MarketplaceAgentSummary[]>([]);
  const [teams, setTeams] = useState<MarketplaceWorkflowRecord[]>([]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [agentRows, teamRows] = await Promise.all([
          listMarketplaceAgents({
            q: searchValue || undefined,
            sort_by: sortBy === "newest" ? "newest" : sortBy === "popular" ? "rating" : "installs",
            limit: 24,
          }),
          listMarketplaceWorkflows({
            q: searchValue || undefined,
            category: category === "all" ? undefined : category,
            sort: sortBy,
            limit: 18,
          }),
        ]);
        setAgents(agentRows || []);
        setTeams(teamRows || []);
      } catch (nextError) {
        setError(String(nextError || "Failed to load marketplace."));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [category, searchValue, sortBy]);

  const filteredAgents = useMemo(() => {
    const activeCategory = category === "all" ? "" : category;
    if (!activeCategory) {
      return agents;
    }
    return agents.filter((item) =>
      String(item.category || item.tags?.[0] || "")
        .toLowerCase()
        .includes(activeCategory),
    );
  }, [agents, category]);

  return (
    <div className="space-y-8">
      <section className="rounded-[28px] border border-black/[0.08] bg-white/85 p-6 shadow-[0_16px_36px_rgba(15,23,42,0.08)]">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5f6c80]">Community Hub</p>
        <h1 className="mt-2 text-[34px] font-semibold tracking-[-0.03em] text-[#0f172a]">
          Discover agents and teams built by the community
        </h1>
        <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto_auto]">
          <input
            value={searchValue}
            onChange={(event) => setSearchValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                const query = searchValue.trim();
                if (query) {
                  onNavigate(`/explore?q=${encodeURIComponent(query)}`);
                }
              }
            }}
            placeholder="Search by use case, connector, or creator..."
            className="h-11 rounded-2xl border border-black/[0.1] bg-white px-4 text-[14px] text-[#111827] outline-none focus:border-[#6366f1]"
          />
          <select
            value={sortBy}
            onChange={(event) => setSortBy(event.target.value as HubSortValue)}
            className="h-11 rounded-2xl border border-black/[0.1] bg-white px-3 text-[13px] font-medium text-[#1f2937] outline-none"
          >
            <option value="trending">Trending</option>
            <option value="newest">Newest</option>
            <option value="popular">Most Installed</option>
          </select>
          <button
            type="button"
            onClick={() => onNavigate("/explore")}
            className="h-11 rounded-2xl border border-[#111827] bg-[#111827] px-4 text-[13px] font-semibold text-white transition hover:bg-[#0b1220]"
          >
            Explore
          </button>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {CATEGORY_TABS.map((tab) => {
            const active = tab === category;
            return (
              <button
                key={tab}
                type="button"
                onClick={() => setCategory(tab)}
                className={`rounded-full px-3 py-1.5 text-[12px] font-semibold capitalize transition ${
                  active ? "bg-[#111827] text-white" : "bg-[#eef2ff] text-[#1f2937] hover:bg-[#e0e7ff]"
                }`}
              >
                {tab}
              </button>
            );
          })}
        </div>
      </section>

      {loading ? <p className="text-[14px] text-[#64748b]">Loading marketplace...</p> : null}
      {error ? <p className="text-[14px] text-[#b42318]">{error}</p> : null}

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[22px] font-semibold tracking-[-0.02em] text-[#111827]">Agents</h2>
          <button
            type="button"
            onClick={() => onNavigate("/explore?type=agents")}
            className="text-[12px] font-semibold text-[#475569] hover:text-[#0f172a]"
          >
            View all
          </button>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filteredAgents.slice(0, 12).map((agent) => (
            <button
              key={agent.agent_id}
              type="button"
              onClick={() => onNavigate(`/marketplace/agents/${encodeURIComponent(agent.agent_id)}`)}
              className="rounded-2xl border border-black/[0.08] bg-white p-4 text-left transition hover:-translate-y-0.5 hover:shadow-[0_12px_24px_rgba(15,23,42,0.08)]"
            >
              <div className="flex items-center gap-3">
                <ConnectorBrandIcon connectorId={agent.agent_id} size={26} />
                <div>
                  <p className="text-[15px] font-semibold text-[#111827]">{agent.name}</p>
                  <p className="text-[12px] text-[#667085]">
                    {agent.creator_display_name || agent.creator_username || "Community"}
                  </p>
                </div>
              </div>
              <p className="mt-3 line-clamp-2 text-[13px] text-[#344054]">{agent.description}</p>
              <div className="mt-3 flex items-center justify-between text-[12px] text-[#64748b]">
                <span>{compactNumber(agent.install_count)} installs</span>
                <span>{Number(agent.avg_rating || 0).toFixed(1)} / 5</span>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[22px] font-semibold tracking-[-0.02em] text-[#111827]">Teams</h2>
          <button
            type="button"
            onClick={() => onNavigate("/explore?type=teams")}
            className="text-[12px] font-semibold text-[#475569] hover:text-[#0f172a]"
          >
            View all
          </button>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {teams.slice(0, 9).map((team) => (
            <button
              key={team.slug}
              type="button"
              onClick={() => onNavigate(`/marketplace/teams/${encodeURIComponent(team.slug)}`)}
              className="rounded-2xl border border-black/[0.08] bg-white p-4 text-left transition hover:-translate-y-0.5 hover:shadow-[0_12px_24px_rgba(15,23,42,0.08)]"
            >
              <p className="text-[15px] font-semibold text-[#111827]">{team.name}</p>
              <p className="mt-0.5 text-[12px] text-[#667085]">
                {team.creator_display_name || team.creator_username || "Community"}
              </p>
              <p className="mt-3 line-clamp-2 text-[13px] text-[#344054]">{team.description}</p>
              <div className="mt-3 flex items-center justify-between text-[12px] text-[#64748b]">
                <span>{compactNumber(team.install_count)} installs</span>
                <span>{team.agent_lineup?.length || 0} agents</span>
              </div>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

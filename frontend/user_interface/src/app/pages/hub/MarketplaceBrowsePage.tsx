import { useEffect, useMemo, useState } from "react";
import { Search, Star, Users } from "lucide-react";

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

const CATEGORIES = [
  { id: "all", label: "All" },
  { id: "analytics", label: "Analytics" },
  { id: "content", label: "Content" },
  { id: "data", label: "Data" },
  { id: "crm", label: "CRM" },
  { id: "support", label: "Support" },
  { id: "automation", label: "Automation" },
];

const SORTS = [
  { id: "trending", label: "Trending" },
  { id: "newest", label: "New" },
  { id: "popular", label: "Popular" },
] as const;

type SortValue = (typeof SORTS)[number]["id"];

function compactNumber(value: number): string {
  const n = Number(value || 0);
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function ratingDisplay(avg: number, count?: number): string {
  if (!avg && !count) return "";
  return `${Number(avg || 0).toFixed(1)}`;
}

export function MarketplaceBrowsePage({ onNavigate }: MarketplaceBrowsePageProps) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [sort, setSort] = useState<SortValue>("trending");
  const [loading, setLoading] = useState(true);
  const [agents, setAgents] = useState<MarketplaceAgentSummary[]>([]);
  const [teams, setTeams] = useState<MarketplaceWorkflowRecord[]>([]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const [a, t] = await Promise.all([
          listMarketplaceAgents({ q: search || undefined, sort_by: sort === "newest" ? "newest" : sort === "popular" ? "rating" : "installs", limit: 24 }),
          listMarketplaceWorkflows({ q: search || undefined, category: category === "all" ? undefined : category, sort, limit: 18 }),
        ]);
        if (!cancelled) { setAgents(a || []); setTeams(t || []); }
      } catch { /* silently fail */ } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [category, search, sort]);

  const filteredAgents = useMemo(() => {
    if (category === "all") return agents;
    return agents.filter((a) => String(a.category || a.tags?.[0] || "").toLowerCase().includes(category));
  }, [agents, category]);

  return (
    <div className="space-y-6">
      {/* Search + filters — one clean row */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[280px] flex-1">
          <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#9ca3af]" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search agents, teams, creators..."
            className="w-full rounded-xl border border-black/[0.08] bg-white py-2.5 pl-10 pr-4 text-[14px] text-[#111827] outline-none placeholder:text-[#9ca3af] focus:border-[#7c3aed]"
          />
        </div>
        <div className="flex items-center gap-1 rounded-xl bg-black/[0.04] p-0.5">
          {SORTS.map((s) => (
            <button key={s.id} type="button" onClick={() => setSort(s.id)}
              className={`rounded-lg px-3 py-1.5 text-[12px] font-medium transition ${sort === s.id ? "bg-white text-[#111827] shadow-sm" : "text-[#667085] hover:text-[#111827]"}`}
            >{s.label}</button>
          ))}
        </div>
      </div>

      {/* Category pills */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {CATEGORIES.map((c) => (
          <button key={c.id} type="button" onClick={() => setCategory(c.id)}
            className={`shrink-0 rounded-full px-3.5 py-1.5 text-[12px] font-semibold transition ${category === c.id ? "bg-[#111827] text-white" : "bg-white border border-black/[0.08] text-[#344054] hover:bg-[#f8fafc]"}`}
          >{c.label}</button>
        ))}
      </div>

      {/* Loading skeleton */}
      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-[140px] animate-pulse rounded-2xl bg-white/60" />
          ))}
        </div>
      ) : null}

      {/* Agents */}
      {!loading && filteredAgents.length > 0 ? (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[16px] font-semibold text-[#111827]">Agents</h2>
            <button type="button" onClick={() => onNavigate("/explore?type=agents")} className="text-[12px] font-medium text-[#7c3aed] hover:underline">View all</button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {filteredAgents.slice(0, 12).map((agent) => {
              const rating = ratingDisplay(agent.avg_rating, agent.rating_count);
              return (
                <button key={agent.agent_id} type="button"
                  onClick={() => onNavigate(`/marketplace/agents/${encodeURIComponent(agent.agent_id)}`)}
                  className="group rounded-2xl border border-black/[0.06] bg-white p-4 text-left transition hover:border-black/[0.12] hover:shadow-md"
                >
                  <div className="flex items-start gap-3">
                    <ConnectorBrandIcon connectorId={agent.agent_id} size={36} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[14px] font-semibold text-[#111827]">{agent.name}</p>
                      <p className="text-[11px] text-[#667085]">{agent.creator_display_name || agent.creator_username || "Community"}</p>
                    </div>
                  </div>
                  <p className="mt-2.5 line-clamp-2 text-[12px] leading-relaxed text-[#475569]">{agent.description}</p>
                  <div className="mt-3 flex items-center gap-3 text-[11px] text-[#94a3b8]">
                    <span>{compactNumber(agent.install_count)} installs</span>
                    {rating ? (
                      <span className="flex items-center gap-0.5">
                        <Star size={10} className="text-[#f59e0b]" fill="#f59e0b" />
                        {rating}
                      </span>
                    ) : null}
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}

      {/* Teams */}
      {!loading && teams.length > 0 ? (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[16px] font-semibold text-[#111827]">Teams</h2>
            <button type="button" onClick={() => onNavigate("/explore?type=teams")} className="text-[12px] font-medium text-[#7c3aed] hover:underline">View all</button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {teams.slice(0, 9).map((team) => {
              const agentCount = team.agent_lineup?.length || 0;
              return (
                <button key={team.slug} type="button"
                  onClick={() => onNavigate(`/marketplace/teams/${encodeURIComponent(team.slug)}`)}
                  className="group rounded-2xl border border-[#e0e7ff] bg-gradient-to-b from-white to-[#f8faff] p-4 text-left transition hover:border-[#c7d2fe] hover:shadow-md"
                >
                  <div className="flex items-start justify-between">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[14px] font-semibold text-[#111827]">{team.name}</p>
                      <p className="text-[11px] text-[#667085]">{team.creator_display_name || team.creator_username || "Community"}</p>
                    </div>
                    {agentCount > 0 ? (
                      <span className="flex shrink-0 items-center gap-1 rounded-full bg-[#f5f3ff] px-2 py-0.5 text-[10px] font-semibold text-[#7c3aed]">
                        <Users size={10} />
                        {agentCount}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-2.5 line-clamp-2 text-[12px] leading-relaxed text-[#475569]">{team.description}</p>
                  <div className="mt-3 flex items-center gap-3 text-[11px] text-[#94a3b8]">
                    <span>{compactNumber(team.install_count)} installs</span>
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}

      {/* Empty state */}
      {!loading && filteredAgents.length === 0 && teams.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-16 text-center">
          <p className="text-[15px] font-medium text-[#344054]">No results found</p>
          <p className="text-[13px] text-[#667085]">Try a different search or category.</p>
          <button type="button" onClick={() => { setSearch(""); setCategory("all"); }} className="text-[13px] font-medium text-[#7c3aed] hover:underline">Clear filters</button>
        </div>
      ) : null}
    </div>
  );
}

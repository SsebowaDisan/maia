import { useEffect, useState } from "react";

import {
  getExploreHome,
  type CreatorProfileRecord,
  type ExploreCategoryRecord,
  type MarketplaceWorkflowRecord,
} from "../../../api/client";

type ExplorePageProps = {
  onNavigate: (path: string) => void;
};

export function ExplorePage({ onNavigate }: ExplorePageProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [trendingAgents, setTrendingAgents] = useState<Array<Record<string, unknown>>>([]);
  const [trendingTeams, setTrendingTeams] = useState<MarketplaceWorkflowRecord[]>([]);
  const [newAgents, setNewAgents] = useState<Array<Record<string, unknown>>>([]);
  const [newTeams, setNewTeams] = useState<MarketplaceWorkflowRecord[]>([]);
  const [categories, setCategories] = useState<ExploreCategoryRecord[]>([]);
  const [featuredCreators, setFeaturedCreators] = useState<CreatorProfileRecord[]>([]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await getExploreHome(8);
        setTrendingAgents(data.trending_agents || []);
        setTrendingTeams(data.trending_teams || []);
        setNewAgents(data.new_agents || []);
        setNewTeams(data.new_teams || []);
        setCategories(data.categories || []);
        setFeaturedCreators(data.featured_creators || []);
      } catch (nextError) {
        setError(String(nextError || "Failed to load explore."));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  if (loading) {
    return <p className="text-[14px] text-[#64748b]">Loading explore...</p>;
  }
  if (error) {
    return <p className="text-[14px] text-[#b42318]">{error}</p>;
  }

  return (
    <div className="space-y-6">
      <section className="rounded-[24px] border border-black/[0.08] bg-white p-6">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#64748b]">Explore</p>
        <h1 className="mt-2 text-[34px] font-semibold tracking-[-0.03em] text-[#111827]">Trending creators, agents, and teams</h1>
      </section>

      <section className="space-y-3">
        <h2 className="text-[21px] font-semibold text-[#111827]">Trending Agents</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {trendingAgents.map((item) => {
            const agentId = String(item.agent_id || item.id || "").trim();
            return (
              <button
                key={agentId}
                type="button"
                onClick={() => onNavigate(`/marketplace/agents/${encodeURIComponent(agentId)}`)}
                className="rounded-xl border border-black/[0.08] bg-white p-3 text-left transition hover:bg-[#eef2ff]"
              >
                <p className="text-[13px] font-semibold text-[#111827]">{String(item.name || agentId)}</p>
                <p className="mt-1 line-clamp-2 text-[12px] text-[#667085]">{String(item.description || "")}</p>
              </button>
            );
          })}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-[21px] font-semibold text-[#111827]">Trending Teams</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {trendingTeams.map((item) => (
            <button
              key={item.slug}
              type="button"
              onClick={() => onNavigate(`/marketplace/teams/${encodeURIComponent(item.slug)}`)}
              className="rounded-xl border border-black/[0.08] bg-white p-3 text-left transition hover:bg-[#eef2ff]"
            >
              <p className="text-[13px] font-semibold text-[#111827]">{item.name}</p>
              <p className="mt-1 line-clamp-2 text-[12px] text-[#667085]">{item.description}</p>
            </button>
          ))}
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        <div className="rounded-[22px] border border-black/[0.08] bg-white p-5">
          <h3 className="text-[17px] font-semibold text-[#111827]">New arrivals</h3>
          <div className="mt-2 space-y-2">
            {newAgents.slice(0, 6).map((item) => {
              const agentId = String(item.agent_id || item.id || "").trim();
              return (
                <button
                  key={agentId}
                  type="button"
                  onClick={() => onNavigate(`/marketplace/agents/${encodeURIComponent(agentId)}`)}
                  className="w-full rounded-lg border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-left text-[12px] text-[#334155] transition hover:bg-[#eef2ff]"
                >
                  {String(item.name || agentId)}
                </button>
              );
            })}
            {newTeams.slice(0, 4).map((item) => (
              <button
                key={item.slug}
                type="button"
                onClick={() => onNavigate(`/marketplace/teams/${encodeURIComponent(item.slug)}`)}
                className="w-full rounded-lg border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-left text-[12px] text-[#334155] transition hover:bg-[#eef2ff]"
              >
                {item.name}
              </button>
            ))}
          </div>
        </div>

        <div className="rounded-[22px] border border-black/[0.08] bg-white p-5">
          <h3 className="text-[17px] font-semibold text-[#111827]">Featured creators</h3>
          <div className="mt-2 space-y-2">
            {featuredCreators.map((creator) => (
              <button
                key={creator.username}
                type="button"
                onClick={() => onNavigate(`/creators/${encodeURIComponent(creator.username)}`)}
                className="w-full rounded-lg border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-left transition hover:bg-[#eef2ff]"
              >
                <p className="text-[13px] font-semibold text-[#111827]">{creator.display_name || creator.username}</p>
                <p className="text-[12px] text-[#667085]">@{creator.username}</p>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-[22px] border border-black/[0.08] bg-white p-5">
        <h3 className="text-[17px] font-semibold text-[#111827]">Browse by category</h3>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {categories.map((category) => (
            <button
              key={category.id}
              type="button"
              onClick={() => onNavigate(`/marketplace?category=${encodeURIComponent(category.id)}`)}
              className="rounded-xl border border-black/[0.08] bg-[#f8fafc] p-3 text-left transition hover:bg-[#eef2ff]"
            >
              <p className="text-[13px] font-semibold text-[#111827]">{category.label}</p>
              <p className="mt-1 text-[12px] text-[#667085]">{(category.agents || []).length} featured agents</p>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

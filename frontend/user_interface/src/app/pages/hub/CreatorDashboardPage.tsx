import { useEffect, useState } from "react";

import { getMyCreatorStats, type CreatorStatsResponse } from "../../../api/client";

type CreatorDashboardPageProps = {
  onNavigate: (path: string) => void;
};

const EMPTY_STATS: CreatorStatsResponse = {
  total_installs: 0,
  published_agent_count: 0,
  published_team_count: 0,
  follower_count: 0,
  top_agents: [],
  top_teams: [],
};

export function CreatorDashboardPage({ onNavigate }: CreatorDashboardPageProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [stats, setStats] = useState<CreatorStatsResponse>(EMPTY_STATS);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await getMyCreatorStats();
        setStats(data || EMPTY_STATS);
      } catch (nextError) {
        setError(String(nextError || "Failed to load dashboard."));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  return (
    <div className="space-y-5">
      <section className="rounded-[24px] border border-black/[0.08] bg-white p-6">
        <h1 className="text-[30px] font-semibold tracking-[-0.03em] text-[#111827]">Creator dashboard</h1>
        <p className="mt-1 text-[14px] text-[#667085]">Monitor installs and manage your published catalog.</p>
      </section>

      {loading ? <p className="text-[14px] text-[#64748b]">Loading dashboard...</p> : null}
      {error ? <p className="text-[14px] text-[#b42318]">{error}</p> : null}

      {!loading ? (
        <>
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-black/[0.08] bg-white p-4">
              <p className="text-[12px] text-[#667085]">Total installs</p>
              <p className="mt-1 text-[24px] font-semibold text-[#111827]">{stats.total_installs}</p>
            </div>
            <div className="rounded-xl border border-black/[0.08] bg-white p-4">
              <p className="text-[12px] text-[#667085]">Published agents</p>
              <p className="mt-1 text-[24px] font-semibold text-[#111827]">{stats.published_agent_count}</p>
            </div>
            <div className="rounded-xl border border-black/[0.08] bg-white p-4">
              <p className="text-[12px] text-[#667085]">Published teams</p>
              <p className="mt-1 text-[24px] font-semibold text-[#111827]">{stats.published_team_count}</p>
            </div>
            <div className="rounded-xl border border-black/[0.08] bg-white p-4">
              <p className="text-[12px] text-[#667085]">Followers</p>
              <p className="mt-1 text-[24px] font-semibold text-[#111827]">{stats.follower_count || 0}</p>
            </div>
          </section>

          <section className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-black/[0.08] bg-white p-4">
              <h2 className="text-[16px] font-semibold text-[#111827]">Top agents</h2>
              <div className="mt-2 space-y-2">
                {(stats.top_agents || []).length ? (
                  stats.top_agents.map((agent) => (
                    <button
                      key={String(agent.agent_id || agent.id || Math.random())}
                      type="button"
                      onClick={() => {
                        const id = String(agent.agent_id || agent.id || "").trim();
                        if (id) {
                          onNavigate(`/marketplace/agents/${encodeURIComponent(id)}`);
                        }
                      }}
                      className="w-full rounded-lg border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-left text-[12px] text-[#334155]"
                    >
                      {String(agent.name || agent.agent_id || "Agent")}
                    </button>
                  ))
                ) : (
                  <p className="text-[12px] text-[#667085]">No published agents yet.</p>
                )}
              </div>
            </div>
            <div className="rounded-xl border border-black/[0.08] bg-white p-4">
              <h2 className="text-[16px] font-semibold text-[#111827]">Top teams</h2>
              <div className="mt-2 space-y-2">
                {(stats.top_teams || []).length ? (
                  stats.top_teams.map((team) => (
                    <button
                      key={String(team.slug || team.id || Math.random())}
                      type="button"
                      onClick={() => {
                        const slug = String(team.slug || "").trim();
                        if (slug) {
                          onNavigate(`/marketplace/teams/${encodeURIComponent(slug)}`);
                        }
                      }}
                      className="w-full rounded-lg border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-left text-[12px] text-[#334155]"
                    >
                      {String(team.name || team.slug || "Team")}
                    </button>
                  ))
                ) : (
                  <p className="text-[12px] text-[#667085]">No published teams yet.</p>
                )}
              </div>
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}

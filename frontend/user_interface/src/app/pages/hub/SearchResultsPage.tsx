import { useEffect, useState } from "react";

import { searchExplore, type ExploreSearchResponse } from "../../../api/client";

type SearchResultsPageProps = {
  query: string;
  onNavigate: (path: string) => void;
};

type SearchTab = "all" | "agents" | "teams" | "creators";

function sanitizeTab(value: string): SearchTab {
  if (value === "agents" || value === "teams" || value === "creators") {
    return value;
  }
  return "all";
}

function readTabFromUrl(): SearchTab {
  const params = new URLSearchParams(window.location.search || "");
  return sanitizeTab(String(params.get("type") || "all").trim().toLowerCase());
}

export function SearchResultsPage({ query, onNavigate }: SearchResultsPageProps) {
  const [tab, setTab] = useState<SearchTab>(() => readTabFromUrl());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState<ExploreSearchResponse | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await searchExplore({ q: query, type: tab, limit: 40 });
        setData(response);
      } catch (nextError) {
        setError(String(nextError || "Search failed."));
      } finally {
        setLoading(false);
      }
    };
    if (!query.trim()) {
      setData({ query: "", agents: [], teams: [], creators: [] });
      setLoading(false);
      return;
    }
    void load();
  }, [query, tab]);

  return (
    <div className="space-y-5">
      <section className="rounded-[24px] border border-black/[0.08] bg-white p-6">
        <h1 className="text-[30px] font-semibold tracking-[-0.03em] text-[#111827]">Search results</h1>
        <p className="mt-1 text-[14px] text-[#667085]">Query: {query || "empty"}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          {(["all", "agents", "teams", "creators"] as const).map((entry) => (
            <button
              key={entry}
              type="button"
              onClick={() => setTab(entry)}
              className={`rounded-full px-3 py-1.5 text-[12px] font-semibold capitalize ${
                tab === entry ? "bg-[#111827] text-white" : "bg-[#eef2ff] text-[#334155]"
              }`}
            >
              {entry}
            </button>
          ))}
        </div>
      </section>

      {loading ? <p className="text-[14px] text-[#64748b]">Searching...</p> : null}
      {error ? <p className="text-[14px] text-[#b42318]">{error}</p> : null}

      {!loading && data ? (
        <section className="grid gap-4 md:grid-cols-2">
          {(tab === "all" || tab === "agents") && (
            <div className="rounded-[20px] border border-black/[0.08] bg-white p-4">
              <h2 className="text-[16px] font-semibold text-[#111827]">Agents</h2>
              <div className="mt-2 space-y-2">
                {(data.agents || []).map((item) => {
                  const agentId = String(item.agent_id || item.id || "").trim();
                  return (
                    <button
                      key={agentId}
                      type="button"
                      onClick={() => onNavigate(`/marketplace/agents/${encodeURIComponent(agentId)}`)}
                      className="w-full rounded-lg border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-left text-[12px] text-[#334155]"
                    >
                      {String(item.name || agentId)}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {(tab === "all" || tab === "teams") && (
            <div className="rounded-[20px] border border-black/[0.08] bg-white p-4">
              <h2 className="text-[16px] font-semibold text-[#111827]">Teams</h2>
              <div className="mt-2 space-y-2">
                {(data.teams || []).map((item) => (
                  <button
                    key={item.slug}
                    type="button"
                    onClick={() => onNavigate(`/marketplace/teams/${encodeURIComponent(item.slug)}`)}
                    className="w-full rounded-lg border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-left text-[12px] text-[#334155]"
                  >
                    {item.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {(tab === "all" || tab === "creators") && (
            <div className="rounded-[20px] border border-black/[0.08] bg-white p-4 md:col-span-2">
              <h2 className="text-[16px] font-semibold text-[#111827]">Creators</h2>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {(data.creators || []).map((item) => (
                  <button
                    key={item.username}
                    type="button"
                    onClick={() => onNavigate(`/creators/${encodeURIComponent(item.username)}`)}
                    className="rounded-lg border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-left"
                  >
                    <p className="text-[13px] font-semibold text-[#111827]">{item.display_name || item.username}</p>
                    <p className="text-[12px] text-[#667085]">@{item.username}</p>
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}

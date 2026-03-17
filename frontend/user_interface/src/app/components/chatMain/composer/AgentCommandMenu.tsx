import { Bot, ChevronRight, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { listAgents, listRecentAgents, type AgentSummaryRecord } from "../../../../api/client";

type AgentCommandSelection = {
  agent_id: string;
  name: string;
  description: string;
  trigger_family: string;
};

type AgentCommandMenuProps = {
  open: boolean;
  onClose: () => void;
  onSelect: (agent: AgentCommandSelection) => void;
};

type IndexedAgent = {
  key: string;
  section: "recent" | "all";
  value: AgentCommandSelection;
};

function normalizeAgent(row: AgentSummaryRecord): AgentCommandSelection | null {
  const agentId = String(row.agent_id || row.id || "").trim();
  if (!agentId) {
    return null;
  }
  return {
    agent_id: agentId,
    name: String(row.name || agentId).trim() || agentId,
    description: String(row.description || "").trim(),
    trigger_family: String(row.trigger_family || "manual").trim().toLowerCase() || "manual",
  };
}

function matchesAgent(agent: AgentCommandSelection, query: string): boolean {
  if (!query) {
    return true;
  }
  const haystack = `${agent.name} ${agent.description}`.toLowerCase();
  return haystack.includes(query);
}

function triggerBadge(triggerFamily: string) {
  if (triggerFamily === "scheduled") {
    return {
      label: "Scheduled",
      className: "border-[#bfdbfe] bg-[#eff6ff] text-[#1d4ed8]",
    };
  }
  return {
    label: "On demand",
    className: "border-black/[0.08] bg-[#f7f7f8] text-[#6e6e73]",
  };
}

function AgentMenuSkeleton() {
  return (
    <div className="space-y-2 p-3">
      {Array.from({ length: 5 }).map((_, index) => (
        <div
          key={`agent-command-skeleton-${String(index)}`}
          className="h-12 animate-pulse rounded-xl border border-black/[0.06] bg-[#f6f6f7]"
        />
      ))}
    </div>
  );
}

function AgentCommandMenu({ open, onClose, onSelect }: AgentCommandMenuProps) {
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [recentAgents, setRecentAgents] = useState<AgentCommandSelection[]>([]);
  const [allAgents, setAllAgents] = useState<AgentCommandSelection[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    if (!open) {
      return;
    }
    let disposed = false;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [recentRows, allRows] = await Promise.all([
          listRecentAgents().catch(() => []),
          listAgents().catch(() => []),
        ]);
        if (disposed) {
          return;
        }
        const normalizedRecent = (recentRows || [])
          .map(normalizeAgent)
          .filter((row): row is AgentCommandSelection => Boolean(row));
        const byId = new Set(normalizedRecent.map((row) => row.agent_id));
        const normalizedAll = (allRows || [])
          .map(normalizeAgent)
          .filter((row): row is AgentCommandSelection => Boolean(row))
          .filter((row) => !byId.has(row.agent_id));
        setRecentAgents(normalizedRecent);
        setAllAgents(normalizedAll);
      } catch (nextError) {
        if (!disposed) {
          setError(String(nextError || "Failed to load agents."));
          setRecentAgents([]);
          setAllAgents([]);
        }
      } finally {
        if (!disposed) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      disposed = true;
    };
  }, [open]);

  const normalizedQuery = search.trim().toLowerCase();
  const visibleRecent = useMemo(
    () => recentAgents.filter((row) => matchesAgent(row, normalizedQuery)),
    [normalizedQuery, recentAgents],
  );
  const visibleAll = useMemo(
    () => allAgents.filter((row) => matchesAgent(row, normalizedQuery)),
    [allAgents, normalizedQuery],
  );
  const indexedRows = useMemo<IndexedAgent[]>(
    () => [
      ...visibleRecent.map((row) => ({
        key: `recent:${row.agent_id}`,
        section: "recent" as const,
        value: row,
      })),
      ...visibleAll.map((row) => ({
        key: `all:${row.agent_id}`,
        section: "all" as const,
        value: row,
      })),
    ],
    [visibleAll, visibleRecent],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    setActiveIndex(0);
  }, [open, normalizedQuery]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (!indexedRows.length) {
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((previous) => (previous + 1) % indexedRows.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((previous) =>
          previous <= 0 ? indexedRows.length - 1 : previous - 1,
        );
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        const selected = indexedRows[activeIndex];
        if (selected) {
          onSelect(selected.value);
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeIndex, indexedRows, onClose, onSelect, open]);

  if (!open) {
    return null;
  }

  const hasRows = indexedRows.length > 0;

  return (
    <div className="absolute bottom-full left-0 z-[140] mb-2 w-[360px] overflow-hidden rounded-2xl border border-black/[0.1] bg-white shadow-[0_18px_42px_-26px_rgba(0,0,0,0.6)]">
      <div className="border-b border-black/[0.06] px-3 py-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
          Agent command
        </p>
        <label className="mt-2 flex h-9 items-center gap-2 rounded-xl border border-black/[0.1] bg-white px-2.5">
          <Search className="h-3.5 w-3.5 text-[#8d8d93]" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search agents"
            className="w-full bg-transparent text-[12px] text-[#1d1d1f] outline-none placeholder:text-[#8d8d93]"
          />
        </label>
      </div>

      {loading ? <AgentMenuSkeleton /> : null}

      {!loading && error ? (
        <div className="p-3">
          <div className="rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#b42318]">
            {error}
          </div>
        </div>
      ) : null}

      {!loading && !error ? (
        <div className="max-h-[320px] overflow-y-auto px-2 py-2">
          {!hasRows ? (
            <a
              href="/marketplace"
              className="flex items-center justify-between rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-[12px] font-semibold text-[#334155]"
            >
              <span>No agents installed yet</span>
              <ChevronRight className="h-3.5 w-3.5" />
            </a>
          ) : (
            <>
              {visibleRecent.length ? (
                <section>
                  <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#8d8d93]">
                    Recent
                  </p>
                  <div className="space-y-1">
                    {visibleRecent.map((agent) => {
                      const key = `recent:${agent.agent_id}`;
                      const currentIndex = indexedRows.findIndex((row) => row.key === key);
                      const isActive = currentIndex === activeIndex;
                      const badge = triggerBadge(agent.trigger_family);
                      return (
                        <button
                          key={key}
                          type="button"
                          onMouseDown={(event) => {
                            event.preventDefault();
                            onSelect(agent);
                          }}
                          onMouseEnter={() => {
                            if (currentIndex >= 0) {
                              setActiveIndex(currentIndex);
                            }
                          }}
                          className={`w-full rounded-xl border px-2.5 py-2 text-left transition-colors ${
                            isActive
                              ? "border-[#c7d2fe] bg-[#eef2ff]"
                              : "border-transparent hover:border-black/[0.06] hover:bg-[#f8f8fa]"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="min-w-0">
                              <p className="truncate text-[13px] font-semibold text-[#111827]">{agent.name}</p>
                              <p className="mt-0.5 truncate text-[12px] text-[#6b7280]">
                                {agent.description || "No description yet."}
                              </p>
                            </div>
                            <span
                              className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}
                            >
                              {badge.label}
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </section>
              ) : null}

              {visibleAll.length ? (
                <section className={visibleRecent.length ? "mt-2" : ""}>
                  <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#8d8d93]">
                    All agents
                  </p>
                  <div className="space-y-1">
                    {visibleAll.map((agent) => {
                      const key = `all:${agent.agent_id}`;
                      const currentIndex = indexedRows.findIndex((row) => row.key === key);
                      const isActive = currentIndex === activeIndex;
                      const badge = triggerBadge(agent.trigger_family);
                      return (
                        <button
                          key={key}
                          type="button"
                          onMouseDown={(event) => {
                            event.preventDefault();
                            onSelect(agent);
                          }}
                          onMouseEnter={() => {
                            if (currentIndex >= 0) {
                              setActiveIndex(currentIndex);
                            }
                          }}
                          className={`w-full rounded-xl border px-2.5 py-2 text-left transition-colors ${
                            isActive
                              ? "border-[#c7d2fe] bg-[#eef2ff]"
                              : "border-transparent hover:border-black/[0.06] hover:bg-[#f8f8fa]"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="min-w-0">
                              <p className="truncate text-[13px] font-semibold text-[#111827]">{agent.name}</p>
                              <p className="mt-0.5 truncate text-[12px] text-[#6b7280]">
                                {agent.description || "No description yet."}
                              </p>
                            </div>
                            <span
                              className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}
                            >
                              {badge.label}
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </section>
              ) : null}
            </>
          )}
        </div>
      ) : null}

      <div className="flex items-center justify-between border-t border-black/[0.06] bg-[#fcfcfd] px-3 py-2">
        <p className="text-[11px] text-[#667085]">Select an agent to route this message.</p>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex items-center gap-1 rounded-full border border-black/[0.08] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#4b5563] hover:bg-[#f7f7f8]"
        >
          <Bot className="h-3.5 w-3.5" />
          Close
        </button>
      </div>
    </div>
  );
}

export { AgentCommandMenu };
export type { AgentCommandMenuProps, AgentCommandSelection };

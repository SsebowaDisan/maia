import { useEffect, useMemo, useState } from "react";
import { Brain, RefreshCw, Trash2, X } from "lucide-react";

import { clearAgentMemory, deleteAgentMemory, listAgentMemory } from "../../../api/client";

type MemoryEntry = {
  id: string;
  content: string;
  tags: string[];
  category: string;
  source: string;
  recordedAt: number;
};

type AgentMemoryTabProps = {
  agentId: string;
};

function toTimestamp(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 10_000_000_000 ? value : value * 1000;
  }
  const parsed = new Date(String(value || "")).getTime();
  return Number.isFinite(parsed) ? parsed : Date.now();
}

function normalizeEntry(row: Record<string, unknown>): MemoryEntry {
  const category = String(row.category || "general").trim() || "general";
  const tags = Array.isArray(row.tags)
    ? row.tags.map((tag) => String(tag || "").trim()).filter(Boolean)
    : [category];
  return {
    id: String(row.id || "").trim(),
    content: String(row.content || row.text || "").trim(),
    tags,
    category,
    source: String(row.source || "memory").trim() || "memory",
    recordedAt: toTimestamp(row.recorded_at || row.created_at),
  };
}

export function AgentMemoryTab({ agentId }: AgentMemoryTabProps) {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [clearing, setClearing] = useState(false);

  const load = async () => {
    if (!agentId) {
      setEntries([]);
      return;
    }
    setLoading(true);
    try {
      const rows = await listAgentMemory({ agentId });
      const normalized = (Array.isArray(rows) ? rows : [])
        .map((row) => normalizeEntry((row || {}) as Record<string, unknown>))
        .filter((row) => Boolean(row.id) && Boolean(row.content))
        .sort((left, right) => right.recordedAt - left.recordedAt);
      setEntries(normalized);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  const sourceCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const entry of entries) {
      counts.set(entry.source, (counts.get(entry.source) || 0) + 1);
    }
    return Array.from(counts.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [entries]);

  const handleDelete = async (memoryId: string) => {
    try {
      await deleteAgentMemory(memoryId);
    } catch {
      // Legacy fallback for older memory ids still tied to agent-specific routes.
      await fetch(`/api/agents/${encodeURIComponent(agentId)}/memory/${encodeURIComponent(memoryId)}`, {
        method: "DELETE",
        credentials: "include",
      });
    }
    setEntries((prev) => prev.filter((entry) => entry.id !== memoryId));
  };

  const handleClear = async () => {
    if (!confirm("Delete all memories for this agent?")) {
      return;
    }
    setClearing(true);
    try {
      await clearAgentMemory();
      await load();
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border/50 px-4 py-3">
        <div className="flex items-center gap-2">
          <Brain size={14} className="text-muted-foreground" />
          <span className="text-sm font-medium">Memory</span>
          {entries.length > 0 ? (
            <span className="text-xs text-muted-foreground">({entries.length})</span>
          ) : null}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => void load()}
            disabled={loading}
            className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-accent disabled:opacity-40"
            title="Refresh"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
          {entries.length > 0 ? (
            <button
              onClick={() => void handleClear()}
              disabled={clearing}
              className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-destructive disabled:opacity-40"
              title="Clear all memories"
            >
              <Trash2 size={12} />
            </button>
          ) : null}
        </div>
      </div>

      {sourceCounts.length > 0 ? (
        <div className="flex flex-wrap gap-1 border-b border-border/30 px-4 py-2">
          {sourceCounts.map(([source, count]) => (
            <span
              key={source}
              className="rounded-full border border-black/[0.08] bg-[#f8fafc] px-2 py-0.5 text-[10px] font-medium text-[#475467]"
            >
              {source}: {count}
            </span>
          ))}
        </div>
      ) : null}

      <div className="flex-1 overflow-y-auto">
        {loading && entries.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
            Loading...
          </div>
        ) : null}

        {!loading && entries.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-12 text-muted-foreground">
            <Brain size={24} className="opacity-30" />
            <span className="text-sm">No memories stored yet</span>
            <span className="px-6 text-center text-xs opacity-60">
              Memories are saved automatically when the agent stores observations during runs.
            </span>
          </div>
        ) : null}

        {entries.map((entry) => (
          <div
            key={entry.id}
            className="group border-b border-border/30 px-4 py-3 transition-colors hover:bg-accent/20"
          >
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-xs leading-relaxed text-foreground">{entry.content}</p>
                <div className="mt-1.5 flex items-center gap-2">
                  {entry.tags.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {entry.tags.map((tag) => (
                        <span
                          key={`${entry.id}-${tag}`}
                          className="inline-block rounded bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <span className="ml-auto text-[10px] text-muted-foreground/50">
                    {new Date(entry.recordedAt).toLocaleString()}
                  </span>
                </div>
              </div>
              <button
                onClick={() => void handleDelete(entry.id)}
                className="shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-destructive group-hover:opacity-100"
                title="Delete memory"
              >
                <X size={11} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

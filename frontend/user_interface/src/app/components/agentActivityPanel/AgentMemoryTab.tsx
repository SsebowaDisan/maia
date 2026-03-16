import { useEffect, useState } from "react";
import { Brain, Trash2, RefreshCw, X } from "lucide-react";

type MemoryEntry = {
  id: string;
  content: string;
  tags: string[];
  recorded_at: number;
};

type AgentMemoryTabProps = {
  agentId: string;
};

export function AgentMemoryTab({ agentId }: AgentMemoryTabProps) {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [clearing, setClearing] = useState(false);

  const load = async () => {
    if (!agentId) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/agents/${agentId}/memory`, { credentials: "include" });
      if (res.ok) {
        const data = await res.json() as MemoryEntry[];
        setEntries(data);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  const handleDelete = async (memoryId: string) => {
    await fetch(`/api/agents/${agentId}/memory/${memoryId}`, {
      method: "DELETE",
      credentials: "include",
    });
    setEntries((prev) => prev.filter((e) => e.id !== memoryId));
  };

  const handleClear = async () => {
    if (!confirm("Delete all memories for this agent?")) return;
    setClearing(true);
    try {
      await fetch(`/api/agents/${agentId}/memory`, {
        method: "DELETE",
        credentials: "include",
      });
      setEntries([]);
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
        <div className="flex items-center gap-2">
          <Brain size={14} className="text-muted-foreground" />
          <span className="text-sm font-medium">Long-term Memory</span>
          {entries.length > 0 && (
            <span className="text-xs text-muted-foreground">({entries.length})</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => void load()}
            disabled={loading}
            className="p-1.5 rounded hover:bg-accent text-muted-foreground transition-colors disabled:opacity-40"
            title="Refresh"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
          {entries.length > 0 && (
            <button
              onClick={() => void handleClear()}
              disabled={clearing}
              className="p-1.5 rounded hover:bg-accent text-muted-foreground hover:text-destructive transition-colors disabled:opacity-40"
              title="Clear all memories"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {loading && entries.length === 0 && (
          <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
            Loading…
          </div>
        )}

        {!loading && entries.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 gap-2 text-muted-foreground">
            <Brain size={24} className="opacity-30" />
            <span className="text-sm">No memories stored yet</span>
            <span className="text-xs opacity-60 text-center px-6">
              Memories are saved automatically when the agent stores observations during runs.
            </span>
          </div>
        )}

        {entries.map((entry) => (
          <div
            key={entry.id}
            className="px-4 py-3 border-b border-border/30 hover:bg-accent/20 transition-colors group"
          >
            <div className="flex items-start gap-2">
              <div className="flex-1 min-w-0">
                <p className="text-xs text-foreground leading-relaxed">{entry.content}</p>
                <div className="flex items-center gap-2 mt-1.5">
                  {entry.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {entry.tags.map((tag) => (
                        <span
                          key={tag}
                          className="inline-block px-1.5 py-0.5 rounded bg-primary/10 text-primary text-[10px]"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                  <span className="text-[10px] text-muted-foreground/50 ml-auto">
                    {new Date(entry.recorded_at * 1000).toLocaleString()}
                  </span>
                </div>
              </div>
              <button
                onClick={() => void handleDelete(entry.id)}
                className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-accent text-muted-foreground hover:text-destructive shrink-0"
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

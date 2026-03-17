import { useEffect, useState, useCallback } from "react";
import { Bell, BellOff, CheckCheck, Trash2, RefreshCw, AlertTriangle, Info, AlertCircle } from "lucide-react";

type InsightSeverity = "info" | "warning" | "critical";

type Insight = {
  id: string;
  signal_type: string;
  severity: InsightSeverity;
  title: string;
  summary: string;
  source_ref: string;
  is_read: boolean;
  created_at: number;
};

const SEVERITY_ICON: Record<InsightSeverity, React.ReactNode> = {
  info: <Info size={14} className="text-violet-400 shrink-0" />,
  warning: <AlertTriangle size={14} className="text-yellow-400 shrink-0" />,
  critical: <AlertCircle size={14} className="text-red-400 shrink-0" />,
};

const SEVERITY_BORDER: Record<InsightSeverity, string> = {
  info: "border-violet-500/30",
  warning: "border-yellow-500/40",
  critical: "border-red-500/50",
};

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: "include" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function apiPost(path: string): Promise<void> {
  await fetch(path, { method: "POST", credentials: "include" });
}

async function apiDelete(path: string): Promise<void> {
  await fetch(path, { method: "DELETE", credentials: "include" });
}

type InsightsFeedPanelProps = {
  className?: string;
};

export function InsightsFeedPanel({ className = "" }: InsightsFeedPanelProps) {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [loading, setLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = unreadOnly ? "?unread_only=true" : "";
      const data = await apiGet<Insight[]>(`/api/insights${params}`);
      setInsights(data);
    } catch {
      // ignore fetch errors — backend may not be ready
    } finally {
      setLoading(false);
    }
  }, [unreadOnly]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleRead = async (id: string) => {
    await apiPost(`/api/insights/${id}/read`);
    setInsights((prev) =>
      prev.map((i) => (i.id === id ? { ...i, is_read: true } : i))
    );
  };

  const handleDelete = async (id: string) => {
    await apiDelete(`/api/insights/${id}`);
    setInsights((prev) => prev.filter((i) => i.id !== id));
  };

  const handleReadAll = async () => {
    await apiPost("/api/insights/read-all");
    setInsights((prev) => prev.map((i) => ({ ...i, is_read: true })));
  };

  const handleTrigger = async () => {
    setTriggering(true);
    try {
      await apiPost("/api/insights/trigger");
      await load();
    } finally {
      setTriggering(false);
    }
  };

  const unreadCount = insights.filter((i) => !i.is_read).length;

  return (
    <div className={`flex flex-col h-full bg-background ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
        <div className="flex items-center gap-2">
          <Bell size={15} className="text-muted-foreground" />
          <span className="text-sm font-medium">Insights</span>
          {unreadCount > 0 && (
            <span className="inline-flex items-center justify-center rounded-full bg-primary text-primary-foreground text-[10px] font-bold px-1.5 min-w-[18px] h-[18px]">
              {unreadCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setUnreadOnly((v) => !v)}
            className={`p-1.5 rounded hover:bg-accent transition-colors ${unreadOnly ? "text-primary" : "text-muted-foreground"}`}
            title={unreadOnly ? "Show all" : "Show unread only"}
          >
            <BellOff size={13} />
          </button>
          {unreadCount > 0 && (
            <button
              onClick={handleReadAll}
              className="p-1.5 rounded hover:bg-accent text-muted-foreground transition-colors"
              title="Mark all read"
            >
              <CheckCheck size={13} />
            </button>
          )}
          <button
            onClick={handleTrigger}
            disabled={triggering}
            className="p-1.5 rounded hover:bg-accent text-muted-foreground transition-colors disabled:opacity-40"
            title="Run signal scan now"
          >
            <RefreshCw size={13} className={triggering ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {loading && insights.length === 0 && (
          <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
            Loading…
          </div>
        )}

        {!loading && insights.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 gap-2 text-muted-foreground">
            <Bell size={24} className="opacity-30" />
            <span className="text-sm">No insights yet</span>
          </div>
        )}

        {insights.map((insight) => (
          <div
            key={insight.id}
            className={`px-4 py-3 border-b border-border/30 border-l-2 ${SEVERITY_BORDER[insight.severity]} ${
              insight.is_read ? "opacity-60" : ""
            } hover:bg-accent/30 transition-colors group`}
          >
            <div className="flex items-start gap-2">
              {SEVERITY_ICON[insight.severity]}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <p className={`text-xs font-medium truncate ${insight.is_read ? "text-muted-foreground" : "text-foreground"}`}>
                    {insight.title}
                  </p>
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                    {!insight.is_read && (
                      <button
                        onClick={() => void handleRead(insight.id)}
                        className="p-1 rounded hover:bg-accent text-muted-foreground"
                        title="Mark read"
                      >
                        <CheckCheck size={11} />
                      </button>
                    )}
                    <button
                      onClick={() => void handleDelete(insight.id)}
                      className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-destructive"
                      title="Delete"
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                </div>
                {insight.summary && (
                  <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">
                    {insight.summary}
                  </p>
                )}
                <p className="text-[10px] text-muted-foreground/50 mt-1">
                  {new Date(insight.created_at * 1000).toLocaleString()}
                  {insight.source_ref ? ` · ${insight.source_ref}` : ""}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

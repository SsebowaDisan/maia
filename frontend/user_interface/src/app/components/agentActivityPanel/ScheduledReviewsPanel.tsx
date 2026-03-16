import { useEffect, useState } from "react";
import {
  CalendarClock,
  Plus,
  Trash2,
  Power,
  Play,
  RefreshCw,
  FileText,
  Loader2,
} from "lucide-react";

type ScheduledReview = {
  id: string;
  name: string;
  agent_id?: string;
  frequency: "weekly" | "monthly";
  enabled: boolean;
  next_run_at: string;
  last_run_at: string | null;
};

type CanvasDoc = {
  id: string;
  title: string;
  updated_at: number;
  source_agent_id: string;
};

const FREQ_LABELS: Record<string, string> = {
  weekly: "Weekly",
  monthly: "Monthly",
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: "include", ...init });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export function ScheduledReviewsPanel() {
  const [schedules, setSchedules] = useState<ScheduledReview[]>([]);
  const [docs, setDocs] = useState<CanvasDoc[]>([]);
  const [loading, setLoading] = useState(false);
  const [triggering, setTriggering] = useState<string | null>(null);

  // Create-form state
  const [showForm, setShowForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newFreq, setNewFreq] = useState<"weekly" | "monthly">("weekly");
  const [creating, setCreating] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [s, d] = await Promise.all([
        api<ScheduledReview[]>("/api/agent/schedules"),
        api<CanvasDoc[]>("/api/documents?limit=10"),
      ]);
      // Filter schedules that look like business reviews
      setSchedules(s.filter((r) => r.name?.toLowerCase().includes("review") || !r.agent_id));
      setDocs(d.filter((d) => d.title?.toLowerCase().includes("review") || d.source_agent_id === "weekly-business-review"));
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAll();
  }, []);

  const handleToggle = async (id: string, enabled: boolean) => {
    try {
      await api(`/api/agent/schedules/${id}/toggle`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !enabled }),
      });
      setSchedules((prev) => prev.map((s) => s.id === id ? { ...s, enabled: !enabled } : s));
    } catch { /* ignore */ }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this schedule?")) return;
    try {
      await api(`/api/agent/schedules/${id}`, { method: "DELETE" });
      setSchedules((prev) => prev.filter((s) => s.id !== id));
    } catch { /* ignore */ }
  };

  const handleTriggerNow = async (id: string) => {
    setTriggering(id);
    try {
      await api(`/api/agent/schedules/${id}/trigger`, { method: "POST" });
      await loadAll();
    } finally {
      setTriggering(null);
    }
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const s = await api<ScheduledReview>("/api/agent/schedules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName,
          prompt: `Generate the Weekly Business Review for ${newName}`,
          frequency: newFreq,
          outputs: ["canvas"],
          channels: [],
        }),
      });
      setSchedules((prev) => [...prev, s]);
      setShowForm(false);
      setNewName("");
    } catch { /* ignore */ } finally {
      setCreating(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
        <div className="flex items-center gap-2">
          <CalendarClock size={14} className="text-muted-foreground" />
          <span className="text-sm font-medium">Business Reviews</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => void loadAll()}
            disabled={loading}
            className="p-1.5 rounded hover:bg-accent text-muted-foreground transition-colors disabled:opacity-40"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
          <button
            onClick={() => setShowForm((v) => !v)}
            className="p-1.5 rounded hover:bg-accent text-muted-foreground transition-colors"
            title="Schedule new review"
          >
            <Plus size={13} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Create form */}
        {showForm && (
          <div className="px-4 py-3 border-b border-border/40 bg-muted/20 space-y-2">
            <p className="text-xs font-medium text-foreground">New scheduled review</p>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Review name…"
              className="w-full text-sm bg-background border border-border/60 rounded px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary/50"
            />
            <div className="flex items-center gap-2">
              <select
                value={newFreq}
                onChange={(e) => setNewFreq(e.target.value as "weekly" | "monthly")}
                className="flex-1 text-sm bg-background border border-border/60 rounded px-2 py-1.5"
              >
                <option value="weekly">Weekly (Mondays)</option>
                <option value="monthly">Monthly</option>
              </select>
              <button
                onClick={() => void handleCreate()}
                disabled={creating || !newName.trim()}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-primary text-primary-foreground text-xs font-medium disabled:opacity-40"
              >
                {creating ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
                Create
              </button>
            </div>
          </div>
        )}

        {/* Schedules */}
        {schedules.length > 0 && (
          <div className="border-b border-border/30">
            <p className="px-4 py-2 text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
              Schedules
            </p>
            {schedules.map((s) => (
              <div key={s.id} className="px-4 py-2.5 flex items-center gap-3 border-b border-border/20 last:border-0 hover:bg-accent/20 group">
                <div className="flex-1 min-w-0">
                  <p className={`text-xs font-medium truncate ${s.enabled ? "text-foreground" : "text-muted-foreground"}`}>
                    {s.name}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    {FREQ_LABELS[s.frequency] ?? s.frequency}
                    {s.next_run_at ? ` · Next: ${new Date(s.next_run_at).toLocaleDateString()}` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => void handleTriggerNow(s.id)}
                    disabled={triggering === s.id}
                    className="p-1 rounded hover:bg-accent text-muted-foreground"
                    title="Run now"
                  >
                    {triggering === s.id ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
                  </button>
                  <button
                    onClick={() => void handleToggle(s.id, s.enabled)}
                    className={`p-1 rounded hover:bg-accent ${s.enabled ? "text-primary" : "text-muted-foreground"}`}
                    title={s.enabled ? "Disable" : "Enable"}
                  >
                    <Power size={11} />
                  </button>
                  <button
                    onClick={() => void handleDelete(s.id)}
                    className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-destructive"
                    title="Delete"
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Recent review documents */}
        {docs.length > 0 && (
          <div>
            <p className="px-4 py-2 text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
              Recent Reports
            </p>
            {docs.map((doc) => (
              <a
                key={doc.id}
                href={`/canvas/${doc.id}`}
                className="flex items-center gap-3 px-4 py-2.5 border-b border-border/20 last:border-0 hover:bg-accent/20 transition-colors"
              >
                <FileText size={12} className="text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-foreground truncate">{doc.title}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {new Date(doc.updated_at * 1000).toLocaleDateString()}
                  </p>
                </div>
              </a>
            ))}
          </div>
        )}

        {!loading && schedules.length === 0 && docs.length === 0 && !showForm && (
          <div className="flex flex-col items-center justify-center py-12 gap-2 text-muted-foreground">
            <CalendarClock size={24} className="opacity-30" />
            <span className="text-sm">No reviews scheduled yet</span>
            <button
              onClick={() => setShowForm(true)}
              className="text-xs text-primary hover:underline"
            >
              + Create your first schedule
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

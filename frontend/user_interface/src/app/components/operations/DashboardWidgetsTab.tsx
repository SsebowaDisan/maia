import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Plus, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  createDashboardWidget,
  deleteDashboardWidget,
  listDashboardWidgets,
  refreshDashboardWidget,
  type DashboardWidgetRecord,
  type AgentSummaryRecord,
} from "../../../api/client";

type DashboardWidgetsTabProps = {
  agents: AgentSummaryRecord[];
};

function toTimeLabel(value: unknown): string {
  const numeric = Number(value);
  if (Number.isFinite(numeric) && numeric > 0) {
    const ms = numeric > 10_000_000_000 ? numeric : numeric * 1000;
    return new Date(ms).toLocaleString();
  }
  return "—";
}

export function DashboardWidgetsTab({ agents }: DashboardWidgetsTabProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [widgets, setWidgets] = useState<DashboardWidgetRecord[]>([]);
  const [title, setTitle] = useState("");
  const [sourceAgentId, setSourceAgentId] = useState("");
  const [content, setContent] = useState("");
  const [refreshingId, setRefreshingId] = useState("");
  const [deletingId, setDeletingId] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await listDashboardWidgets();
      setWidgets(Array.isArray(rows) ? rows : []);
    } catch (error) {
      toast.error(`Failed to load dashboard widgets: ${String(error)}`);
      setWidgets([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const sortedWidgets = useMemo(
    () =>
      [...widgets].sort((left, right) => {
        const leftPos = Number(left.position ?? 0);
        const rightPos = Number(right.position ?? 0);
        if (leftPos !== rightPos) {
          return leftPos - rightPos;
        }
        const leftTs = Number(left.last_refreshed_at || left.created_at || 0);
        const rightTs = Number(right.last_refreshed_at || right.created_at || 0);
        return rightTs - leftTs;
      }),
    [widgets],
  );

  const addWidget = async () => {
    const cleanTitle = String(title || "").trim();
    if (!cleanTitle) {
      toast.error("Widget title is required.");
      return;
    }
    setSaving(true);
    try {
      const created = await createDashboardWidget({
        title: cleanTitle,
        source_agent_id: sourceAgentId.trim(),
        content: content.trim(),
      });
      setWidgets((prev) => [created, ...prev]);
      setTitle("");
      setContent("");
      toast.success("Widget pinned to dashboard.");
    } catch (error) {
      toast.error(`Failed to create widget: ${String(error)}`);
    } finally {
      setSaving(false);
    }
  };

  const handleRefreshWidget = async (widgetId: string) => {
    setRefreshingId(widgetId);
    try {
      const refreshed = await refreshDashboardWidget(widgetId);
      setWidgets((prev) =>
        prev.map((row) => (row.id === widgetId ? refreshed : row)),
      );
    } catch (error) {
      toast.error(`Widget refresh failed: ${String(error)}`);
    } finally {
      setRefreshingId("");
    }
  };

  const handleDeleteWidget = async (widgetId: string) => {
    setDeletingId(widgetId);
    try {
      await deleteDashboardWidget(widgetId);
      setWidgets((prev) => prev.filter((row) => row.id !== widgetId));
    } catch (error) {
      toast.error(`Failed to delete widget: ${String(error)}`);
    } finally {
      setDeletingId("");
    }
  };

  return (
    <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
            Dashboard
          </p>
          <p className="mt-1 text-[13px] text-[#475467]">
            Pin important outputs and refresh them live.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            void load();
          }}
          className="inline-flex items-center gap-1 rounded-full border border-black/[0.1] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#344054] hover:bg-[#f8fafc]"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-4">
        <label className="lg:col-span-2">
          <span className="text-[12px] font-semibold text-[#344054]">Widget title</span>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Weekly campaign summary"
            className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
          />
        </label>
        <label>
          <span className="text-[12px] font-semibold text-[#344054]">Source agent</span>
          <select
            value={sourceAgentId}
            onChange={(event) => setSourceAgentId(event.target.value)}
            className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
          >
            <option value="">None</option>
            {agents.map((agent) => (
              <option key={agent.agent_id} value={agent.agent_id}>
                {agent.name} ({agent.agent_id})
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="text-[12px] font-semibold text-[#344054]">Initial content</span>
          <input
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder="Optional starter text"
            className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
          />
        </label>
      </div>

      <button
        type="button"
        onClick={() => {
          void addWidget();
        }}
        disabled={saving}
        className="mt-3 inline-flex items-center gap-1 rounded-full bg-[#7c3aed] px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-60"
      >
        {saving ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
        Pin widget
      </button>

      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        {loading && widgets.length === 0 ? (
          <p className="rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-[12px] text-[#667085]">
            Loading dashboard widgets...
          </p>
        ) : null}

        {!loading && sortedWidgets.length === 0 ? (
          <p className="rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-[12px] text-[#667085]">
            No widgets pinned yet.
          </p>
        ) : null}

        {sortedWidgets.map((widget) => (
          <article
            key={widget.id}
            className="rounded-xl border border-black/[0.08] bg-[#fcfcfd] p-3"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-[14px] font-semibold text-[#111827]">{widget.title}</p>
                <p className="mt-0.5 text-[11px] text-[#667085]">
                  {widget.source_agent_id ? `Agent: ${widget.source_agent_id}` : "Manual widget"}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => {
                    void handleRefreshWidget(widget.id);
                  }}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-black/[0.1] text-[#344054] hover:bg-[#f8fafc]"
                  title="Refresh widget"
                >
                  {refreshingId === widget.id ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <RefreshCw size={12} />
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    void handleDeleteWidget(widget.id);
                  }}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-[#fecaca] text-[#b42318] hover:bg-[#fff1f2]"
                  title="Delete widget"
                >
                  {deletingId === widget.id ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Trash2 size={12} />
                  )}
                </button>
              </div>
            </div>

            <p className="mt-2 whitespace-pre-wrap text-[12px] leading-[1.5] text-[#1f2937]">
              {String(widget.content || "").trim() || "No output captured yet."}
            </p>

            <p className="mt-2 text-[10px] text-[#98a2b3]">
              Last refreshed: {toTimeLabel(widget.last_refreshed_at || widget.created_at)}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, RefreshCw, Users } from "lucide-react";

import { listRunCollaboration, type CollaborationEntry } from "../../../api/client";
import type { AgentActivityEvent } from "../../types";

type TeamConversationTabProps = {
  runId: string;
  events: AgentActivityEvent[];
};

function toTimestamp(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 10_000_000_000 ? value : value * 1000;
  }
  const parsed = new Date(String(value || "")).getTime();
  return Number.isFinite(parsed) ? parsed : Date.now();
}

function deriveFromEvents(events: AgentActivityEvent[]): CollaborationEntry[] {
  const rows: CollaborationEntry[] = [];
  for (const event of events) {
    const type = String(event.event_type || "").trim().toLowerCase();
    if (type !== "agent_collaboration" && type !== "agent_handoff" && type !== "agent.handoff") {
      continue;
    }
    const data = ((event.data ?? event.metadata) ?? {}) as Record<string, unknown>;
    const fromAgent = String(
      data.from_agent || data.source_agent || data.agent_id || event.metadata?.agent_id || "Agent",
    ).trim();
    const toAgent = String(data.to_agent || data.target_agent || data.next_agent || "Agent").trim();
    const message = String(
      data.message || data.summary || event.detail || event.title || "Agent collaboration update",
    ).trim();
    rows.push({
      run_id: event.run_id,
      from_agent: fromAgent || "Agent",
      to_agent: toAgent || "Agent",
      message,
      entry_type: type.includes("handoff") ? "handoff" : "message",
      timestamp: toTimestamp(data.timestamp || event.ts || event.timestamp),
      metadata: data,
    });
  }
  return rows;
}

export function TeamConversationTab({ runId, events }: TeamConversationTabProps) {
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [rows, setRows] = useState<CollaborationEntry[]>([]);

  const fallbackRows = useMemo(() => deriveFromEvents(events), [events]);

  const load = useCallback(async () => {
    if (!runId) {
      setRows([]);
      return;
    }
    setLoading(true);
    setLoadError("");
    try {
      const remoteRows = await listRunCollaboration(runId);
      if (Array.isArray(remoteRows) && remoteRows.length > 0) {
        setRows(
          [...remoteRows].sort(
            (left, right) => toTimestamp(left.timestamp) - toTimestamp(right.timestamp),
          ),
        );
      } else {
        setRows(fallbackRows);
      }
    } catch (error) {
      setLoadError(String(error || "Failed to load collaboration logs."));
      setRows(fallbackRows);
    } finally {
      setLoading(false);
    }
  }, [fallbackRows, runId]);

  useEffect(() => {
    void load();
  }, [load]);

  const hasRows = rows.length > 0;

  return (
    <section className="mt-3 rounded-2xl border border-[#e5e7eb] bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-[#111827]">
          <Users size={14} />
          <p className="text-[13px] font-semibold">Team conversation</p>
          {hasRows ? (
            <span className="rounded-full border border-[#e4e7ec] bg-[#f8fafc] px-2 py-0.5 text-[10px] font-semibold text-[#475467]">
              {rows.length}
            </span>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => {
            void load();
          }}
          className="inline-flex items-center gap-1 rounded-full border border-[#d0d5dd] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#344054] hover:bg-[#f9fafb]"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {loading && !hasRows ? (
        <div className="flex items-center gap-2 rounded-xl border border-[#eaecf0] bg-[#f8fafc] px-3 py-2 text-[12px] text-[#475467]">
          <Loader2 size={13} className="animate-spin" />
          Loading collaboration logs...
        </div>
      ) : null}

      {loadError ? (
        <p className="mb-2 rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#b42318]">
          {loadError}
        </p>
      ) : null}

      {!loading && !hasRows ? (
        <p className="rounded-xl border border-[#eaecf0] bg-[#f8fafc] px-3 py-2 text-[12px] text-[#667085]">
          No agent-to-agent messages were recorded for this run yet.
        </p>
      ) : null}

      {hasRows ? (
        <div className="max-h-[260px] space-y-2 overflow-y-auto pr-1">
          {rows.map((row, index) => {
            const from = String(row.from_agent || "Agent").trim() || "Agent";
            const to = String(row.to_agent || "Agent").trim() || "Agent";
            const message = String(row.message || "").trim() || "Update";
            const handoff = String(row.entry_type || "").toLowerCase().includes("handoff");
            return (
              <article
                key={`${from}-${to}-${toTimestamp(row.timestamp)}-${index}`}
                className={`rounded-xl border px-3 py-2 ${
                  handoff
                    ? "border-[#fde68a] bg-[#fffbeb]"
                    : "border-[#e4e7ec] bg-[#f8fafc]"
                }`}
              >
                <div className="flex items-center gap-2 text-[11px] font-semibold">
                  <span className="rounded-full bg-white px-2 py-0.5 text-[#344054]">{from}</span>
                  <span className="text-[#98a2b3]">→</span>
                  <span className="rounded-full bg-white px-2 py-0.5 text-[#344054]">{to}</span>
                  <span className="ml-auto text-[10px] font-medium text-[#98a2b3]">
                    {new Date(toTimestamp(row.timestamp)).toLocaleTimeString()}
                  </span>
                </div>
                <p className="mt-1 text-[12px] leading-[1.5] text-[#1f2937]">{message}</p>
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}

import { useMemo, useState, type RefObject } from "react";

import type { AgentActivityEvent } from "../../types";
import type { WorkspaceRenderMode } from "./workspaceRenderModes";

type WorkspaceLogPanelProps = {
  activityEvents: AgentActivityEvent[];
  renderedInfoHtml: string;
  infoHtmlRef: RefObject<HTMLDivElement | null>;
  workspaceRenderMode: WorkspaceRenderMode;
};

type EventSummaryRow = {
  eventId: string;
  eventIndex: number;
  eventType: string;
  title: string;
  detail: string;
  family: string;
  replayImportance: string;
  agentLabel: string;
};

function cleanText(value: unknown): string {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function summarizeEvent(event: AgentActivityEvent): EventSummaryRow {
  const data = asRecord(event.data);
  const eventIndex = Number(event.event_index || data.event_index || event.seq || 0);
  const family = cleanText(event.event_family || data.event_family || "system");
  const replayImportance = cleanText(
    event.replay_importance || data.replay_importance || event.event_replay_importance || data.event_replay_importance || "normal",
  );
  const agentLabel = cleanText(data.agent_label || data.agent_role || data.owner_role || "system");
  return {
    eventId: cleanText(event.event_id),
    eventIndex: Number.isFinite(eventIndex) && eventIndex > 0 ? eventIndex : 0,
    eventType: cleanText(event.event_type || event.type || "event"),
    title: cleanText(event.title || event.event_type || event.type || "Event"),
    detail: cleanText(event.detail || ""),
    family,
    replayImportance,
    agentLabel,
  };
}

function WorkspaceLogPanel({
  activityEvents,
  renderedInfoHtml,
  infoHtmlRef,
  workspaceRenderMode,
}: WorkspaceLogPanelProps) {
  const [selectedAgent, setSelectedAgent] = useState("all");
  const [selectedFamily, setSelectedFamily] = useState("all");
  const [selectedImportance, setSelectedImportance] = useState("all");

  const eventRows = useMemo(
    () =>
      activityEvents
        .map((event) => summarizeEvent(event))
        .sort((left, right) => right.eventIndex - left.eventIndex),
    [activityEvents],
  );

  const agentOptions = useMemo(() => {
    const values = new Set<string>();
    for (const row of eventRows) {
      if (row.agentLabel) {
        values.add(row.agentLabel);
      }
    }
    return ["all", ...Array.from(values).sort()];
  }, [eventRows]);

  const familyOptions = useMemo(() => {
    const values = new Set<string>();
    for (const row of eventRows) {
      if (row.family) {
        values.add(row.family);
      }
    }
    return ["all", ...Array.from(values).sort()];
  }, [eventRows]);

  const importanceOptions = useMemo(() => {
    const values = new Set<string>();
    for (const row of eventRows) {
      if (row.replayImportance) {
        values.add(row.replayImportance);
      }
    }
    return ["all", ...Array.from(values).sort()];
  }, [eventRows]);

  const filteredRows = useMemo(
    () =>
      eventRows
        .filter((row) => selectedAgent === "all" || row.agentLabel === selectedAgent)
        .filter((row) => selectedFamily === "all" || row.family === selectedFamily)
        .filter((row) => selectedImportance === "all" || row.replayImportance === selectedImportance)
        .slice(
          0,
          workspaceRenderMode === "fast"
            ? 20
            : workspaceRenderMode === "balanced"
              ? 80
              : 180,
        ),
    [eventRows, selectedAgent, selectedFamily, selectedImportance, workspaceRenderMode],
  );

  return (
    <div className="space-y-3 rounded-2xl border border-black/[0.08] bg-white p-3 shadow-sm">
      <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Execution logs</p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <select
          value={selectedAgent}
          onChange={(event) => setSelectedAgent(event.target.value)}
          className="rounded-lg border border-black/[0.08] bg-[#fafafc] px-2 py-1.5 text-[11px] text-[#1d1d1f]"
        >
          {agentOptions.map((option) => (
            <option key={option} value={option}>
              {option === "all" ? "All agents" : option}
            </option>
          ))}
        </select>
        <select
          value={selectedFamily}
          onChange={(event) => setSelectedFamily(event.target.value)}
          className="rounded-lg border border-black/[0.08] bg-[#fafafc] px-2 py-1.5 text-[11px] text-[#1d1d1f]"
        >
          {familyOptions.map((option) => (
            <option key={option} value={option}>
              {option === "all" ? "All families" : option}
            </option>
          ))}
        </select>
        <select
          value={selectedImportance}
          onChange={(event) => setSelectedImportance(event.target.value)}
          className="rounded-lg border border-black/[0.08] bg-[#fafafc] px-2 py-1.5 text-[11px] text-[#1d1d1f]"
        >
          {importanceOptions.map((option) => (
            <option key={option} value={option}>
              {option === "all" ? "All importance" : option}
            </option>
          ))}
        </select>
      </div>

      <div className="max-h-[180px] space-y-1.5 overflow-auto rounded-lg border border-black/[0.06] bg-[#fafafc] p-2">
        {filteredRows.length > 0 ? (
          filteredRows.map((row) => (
            <div key={row.eventId || `${row.eventIndex}-${row.eventType}`} className="rounded-md border border-black/[0.06] bg-white px-2 py-1.5">
              <p className="truncate text-[11px] font-medium text-[#1d1d1f]">
                {row.eventIndex > 0 ? `#${row.eventIndex} ` : ""}
                {row.title}
              </p>
              <p className="truncate text-[10px] text-[#6e6e73]">
                {row.agentLabel || "system"} | {row.family || "system"} | {row.replayImportance || "normal"}
              </p>
            </div>
          ))
        ) : (
          <div className="rounded-md border border-black/[0.06] bg-white px-2 py-1.5 text-[11px] text-[#6e6e73]">
            No events match the selected filters.
          </div>
        )}
      </div>

      {workspaceRenderMode !== "fast" && renderedInfoHtml.trim() ? (
        <div ref={infoHtmlRef} className="max-h-[380px] overflow-auto rounded-lg border border-black/[0.06] bg-white p-3">
          <div
            className="chat-answer-html assistantAnswerBody info-panel-answer-html text-[13px] leading-[1.5] text-[#1d1d1f]"
            dangerouslySetInnerHTML={{ __html: renderedInfoHtml }}
          />
        </div>
      ) : workspaceRenderMode === "fast" ? (
        <div className="rounded-lg border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
          Fast mode hides full markup details to keep replay density low.
        </div>
      ) : (
        <div className="rounded-lg border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
          This run did not provide rendered evidence HTML.
        </div>
      )}
    </div>
  );
}

export { WorkspaceLogPanel };

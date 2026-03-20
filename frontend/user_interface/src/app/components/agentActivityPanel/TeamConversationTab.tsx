import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, RefreshCw, Users } from "lucide-react";

import { listRunCollaboration, type CollaborationEntry } from "../../../api/client";
import { readEventPayload } from "../../utils/eventPayload";
import type { AgentActivityEvent } from "../../types";
import {
  EVT_AGENT_DIALOGUE_RESOLVED,
  EVT_AGENT_DIALOGUE_STARTED,
  EVT_AGENT_DIALOGUE_TURN,
  EVT_BRAIN_ANSWER_RECEIVED,
  EVT_BRAIN_QUESTION,
  EVT_BRAIN_REVIEW_DECISION,
  EVT_BRAIN_REVIEW_STARTED,
  EVT_BRAIN_REVISION_REQUESTED,
} from "../../constants/eventTypes";

type TeamConversationTabProps = {
  runId?: string;
  events: AgentActivityEvent[];
};

const FALLBACK_EVENT_TYPES = new Set<string>([
  "assembly_brain_thinking",
  "assembly_narration",
  "assembly_connector_needed",
  "assembly_schedule_detected",
  "assembly_started",
  "assembly_step_added",
  "assembly_edge_added",
  "assembly_complete",
  "assembly_completed",
  "assembly_error",
  "workflow_saved",
  "workflow_step_started",
  "workflow_step_completed",
  "workflow_step_failed",
  "execution_starting",
  "execution_checkpoint",
  "execution_complete",
  "execution_error",
  "agent_collaboration",
  "agent_handoff",
  "agent.handoff",
  "agent.resume",
  "agent.waiting",
  "brain_thinking",
  "brain_rationale",
  "role_handoff",
  "role_activated",
  "role_contract_check",
  "research_branch_started",
  "execution_checkpoint",
  "workflow_steps_unblocked",
  "llm.plan_step",
  "llm.plan_fact_coverage",
  "brain_review_summary",
  "tool_started",
  "tool_progress",
  "tool_completed",
  "tool_failed",
  "tool_skipped",
  EVT_AGENT_DIALOGUE_TURN,
  EVT_AGENT_DIALOGUE_STARTED,
  EVT_AGENT_DIALOGUE_RESOLVED,
  EVT_BRAIN_REVIEW_STARTED,
  EVT_BRAIN_REVIEW_DECISION,
  EVT_BRAIN_REVISION_REQUESTED,
  EVT_BRAIN_QUESTION,
  EVT_BRAIN_ANSWER_RECEIVED,
]);

function toTimestamp(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 10_000_000_000 ? value : value * 1000;
  }
  const parsed = new Date(String(value || "")).getTime();
  return Number.isFinite(parsed) ? parsed : Date.now();
}

function normalizeEntryType(row: CollaborationEntry): string {
  const raw = String(row.entry_type || "").trim().toLowerCase();
  if (raw === "response") {
    return "answer";
  }
  if (raw === "request") {
    return "question";
  }
  if (raw === "integration") {
    return "dialogue";
  }
  if (raw === "disagreement") {
    return "challenge";
  }
  return raw || "message";
}

function rowTypeFromEvent(type: string, data: Record<string, unknown>): string {
  const toolId = String(data.tool_id || data.tool || "").trim().toLowerCase();
  if (type.startsWith("tool_") && toolId.includes("agent.delegate")) {
    return "handoff";
  }
  if (type === "assembly_step_added" || type.includes("handoff")) {
    return "handoff";
  }
  if (type.startsWith("assembly_")) {
    return "message";
  }
  if (type === EVT_BRAIN_REVISION_REQUESTED) {
    return "revision";
  }
  if (type === EVT_BRAIN_QUESTION) {
    return "question";
  }
  if (type === EVT_BRAIN_ANSWER_RECEIVED) {
    return "answer";
  }
  if (type.startsWith("brain_review")) {
    return "review";
  }
  if (type.startsWith("agent_dialogue")) {
    const turnRole = String(data.turn_role || "").trim().toLowerCase();
    if (turnRole === "request") {
      return "question";
    }
    if (turnRole === "response") {
      return "answer";
    }
    if (turnRole === "integration") {
      return "dialogue";
    }
    if (turnRole === "handoff") {
      return "handoff";
    }
    if (turnRole === "review") {
      return "review";
    }
    const turnType = String(data.turn_type || "").trim().toLowerCase();
    if (turnType === "question" || turnType.endsWith("_request") || turnType.endsWith("_question")) {
      return "question";
    }
    if (turnType === "answer" || turnType === "response" || turnType.endsWith("_response") || turnType.endsWith("_answer")) {
      return "answer";
    }
    if (turnType === "handoff") {
      return "handoff";
    }
    return "dialogue";
  }
  return "message";
}

function humanizeToken(value: unknown, fallback = ""): string {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) {
    return fallback;
  }
  return raw
    .replace(/[_\-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function speakerName(value: unknown, fallback: string): string {
  const raw = String(value || "").trim();
  if (!raw) {
    return fallback;
  }
  if (raw.toLowerCase() === "brain") {
    return "Brain";
  }
  const tokens = raw
    .split(/[_\-. ]+/)
    .map((token) => token.trim())
    .filter(Boolean);
  if (!tokens.length) {
    return fallback;
  }
  return tokens
    .map((token) => `${token.charAt(0).toUpperCase()}${token.slice(1)}`)
    .join(" ");
}

function sourceAgentForEvent(type: string, data: Record<string, unknown>, event: AgentActivityEvent): string {
  if (type.startsWith("assembly_")) {
    return "Brain";
  }
  if (type.startsWith("brain_")) {
    return "Brain";
  }
  return speakerName(
    data.from_agent ||
      data.source_agent ||
      data.from_role ||
      data.owner_role ||
      data.agent_role ||
      data.agent_id ||
      data.role ||
      event.metadata?.owner_role ||
      event.metadata?.from_agent ||
      event.metadata?.agent_role ||
      event.metadata?.step_agent_id ||
      event.metadata?.agent_id ||
      event.data?.owner_role ||
      event.data?.from_agent ||
      event.data?.agent_role ||
      event.data?.agent_id,
    "Agent",
  );
}

function targetAgentForEvent(type: string, data: Record<string, unknown>, fromAgent: string): string {
  if (type === "assembly_step_added") {
    return speakerName(data.agent_role || data.step_agent_id || data.step_role, "Agent");
  }
  if (type === "assembly_connector_needed") {
    return "Connector setup";
  }
  if (type.startsWith("tool_")) {
    const toolLabel = String(data.tool_label || data.tool_id || data.tool || "").trim();
    if (toolLabel) {
      return speakerName(toolLabel, "Tool");
    }
  }
  return speakerName(
    data.to_agent ||
      data.target_agent ||
      data.child_agent_id ||
      data.next_agent ||
      data.next_role ||
      data.agent_role ||
      data.to_role,
    fromAgent.toLowerCase() === "brain" ? "Team" : "Agent",
  );
}

function messageForEvent(type: string, data: Record<string, unknown>, event: AgentActivityEvent): string {
  if (type === "assembly_step_added") {
    const role = speakerName(data.agent_role || data.step_agent_id || data.step_role, "");
    const description = String(data.description || event.detail || "").trim();
    if (role && description) {
      return `Assigning ${role}: ${description}`;
    }
  }
  if (type === "assembly_edge_added") {
    const fromStep = String(data.from_step || data.from || "").trim();
    const toStep = String(data.to_step || data.to || "").trim();
    if (fromStep && toStep) {
      return `Linking ${fromStep} -> ${toStep}`;
    }
  }
  if (type === EVT_BRAIN_REVIEW_DECISION) {
    const decision = String(data.decision || "").trim();
    const reasoning = String(data.reasoning || data.reason || "").trim();
    if (decision && reasoning) {
      return `${decision}: ${reasoning}`;
    }
  }
  if (type === "workflow_step_started" || type === "workflow_step_completed") {
    const stepId = String(data.step_id || "").trim();
    const detail = String(event.detail || data.detail || "").trim();
    if (stepId && detail) {
      return `${stepId}: ${detail}`;
    }
  }
  return String(
    data.message ||
      data.summary ||
      data.reasoning ||
      data.feedback ||
      data.question ||
      data.answer ||
      data.recovery_hint ||
      event.detail ||
      event.title ||
      "Agent collaboration update",
  ).trim();
}

function deriveFromEvents(events: AgentActivityEvent[]): CollaborationEntry[] {
  const rows: CollaborationEntry[] = [];
  for (const event of events) {
    const type = String(event.event_type || event.type || "").trim().toLowerCase();
    if (!FALLBACK_EVENT_TYPES.has(type)) {
      continue;
    }
    const data = readEventPayload(event);
    const fromAgent = sourceAgentForEvent(type, data, event);
    const resolvedToAgent = targetAgentForEvent(type, data, fromAgent);
    const message = messageForEvent(type, data, event);
    rows.push({
      run_id: event.run_id,
      from_agent: fromAgent,
      to_agent: resolvedToAgent,
      message,
      entry_type: rowTypeFromEvent(type, data),
      timestamp: toTimestamp(data.timestamp || event.ts || event.timestamp),
      metadata: { ...data, event_id: event.event_id, event_type: type },
    });
  }
  return rows;
}

function mergeRows(remoteRows: CollaborationEntry[], fallbackRows: CollaborationEntry[]): CollaborationEntry[] {
  const merged = new Map<string, CollaborationEntry>();
  for (const row of [...remoteRows, ...fallbackRows]) {
    const timestamp = toTimestamp(row.timestamp);
    const eventId = String(
      (row.metadata as Record<string, unknown> | undefined)?.event_id || "",
    ).trim();
    const key = [
      String(row.from_agent || "").trim().toLowerCase(),
      String(row.to_agent || "").trim().toLowerCase(),
      String(row.message || "").trim().toLowerCase(),
      normalizeEntryType(row),
      String(timestamp),
      eventId,
    ].join("|");
    merged.set(key, {
      ...row,
      entry_type: normalizeEntryType(row),
      timestamp,
    });
  }
  return [...merged.values()].sort((left, right) => toTimestamp(left.timestamp) - toTimestamp(right.timestamp));
}

function avatarSeed(name: string): string {
  let hash = 0;
  for (let index = 0; index < name.length; index += 1) {
    hash = (hash << 5) - hash + name.charCodeAt(index);
    hash |= 0;
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue} 70% 92%)`;
}

function initials(name: string): string {
  const tokens = String(name || "")
    .trim()
    .split(/[\s_\-.]+/)
    .filter(Boolean);
  if (!tokens.length) {
    return "A";
  }
  if (tokens.length === 1) {
    return tokens[0].slice(0, 2).toUpperCase();
  }
  return `${tokens[0][0] || ""}${tokens[1][0] || ""}`.toUpperCase();
}

function bubbleClass(entryType: string, fromAgent: string): string {
  const from = String(fromAgent || "").trim().toLowerCase();
  if (from === "brain") {
    return "border-[#c7d2fe] bg-[#eef2ff]";
  }
  if (entryType === "handoff") {
    return "border-[#fde68a] bg-[#fffbeb]";
  }
  if (entryType === "question") {
    return "border-[#bfdbfe] bg-[#eff6ff]";
  }
  if (entryType === "answer") {
    return "border-[#bbf7d0] bg-[#ecfdf3]";
  }
  if (entryType === "challenge" || entryType === "revision") {
    return "border-[#fed7aa] bg-[#fff7ed]";
  }
  if (entryType === "review") {
    return "border-[#ddd6fe] bg-[#f5f3ff]";
  }
  return "border-[#e4e7ec] bg-[#f8fafc]";
}

function routeLabel(from: string, to: string): string {
  const source = String(from || "").trim().toLowerCase();
  const target = String(to || "").trim();
  if (!target) {
    return "team update";
  }
  if (source === target.toLowerCase()) {
    return "self note";
  }
  if (target.toLowerCase() === "team") {
    return "to team";
  }
  return `to ${target}`;
}

function entryLabel(entryType: string): string {
  if (entryType === "handoff") return "handoff";
  if (entryType === "question") return "question";
  if (entryType === "answer") return "answer";
  if (entryType === "challenge") return "challenge";
  if (entryType === "revision") return "revision";
  if (entryType === "review") return "review";
  if (entryType === "dialogue") return "dialogue";
  return "message";
}

function badgeLabel(row: CollaborationEntry, entryType: string): string {
  const metadata = row.metadata as Record<string, unknown> | undefined;
  const interactionLabel = humanizeToken(
    metadata?.interaction_label || metadata?.turn_type,
    "",
  );
  if (interactionLabel) {
    return interactionLabel;
  }
  return entryLabel(entryType);
}

export function TeamConversationTab({ runId, events }: TeamConversationTabProps) {
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [remoteRows, setRemoteRows] = useState<CollaborationEntry[]>([]);

  const fallbackRows = useMemo(() => deriveFromEvents(events), [events]);
  const rows = useMemo(
    () => mergeRows(remoteRows, fallbackRows),
    [fallbackRows, remoteRows],
  );

  const load = useCallback(async () => {
    const normalizedRunId = String(runId || "").trim();
    if (!normalizedRunId) {
      setRemoteRows([]);
      setLoading(false);
      setLoadError("");
      return;
    }
    setLoading(true);
    setLoadError("");
    try {
      const nextRows = await listRunCollaboration(normalizedRunId);
      setRemoteRows(Array.isArray(nextRows) ? nextRows : []);
    } catch (error) {
      const message = String(error || "Failed to load collaboration logs.");
      if (!fallbackRows.length) {
        setLoadError(message);
      } else {
        setLoadError("");
      }
      setRemoteRows([]);
    } finally {
      setLoading(false);
    }
  }, [fallbackRows.length, runId]);

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
        <div className="max-h-[340px] space-y-2 overflow-y-auto pr-1">
          {rows.map((row, index) => {
            const from = String(row.from_agent || "Agent").trim() || "Agent";
            const to = String(row.to_agent || "Agent").trim() || "Agent";
            const message = String(row.message || "").trim() || "Update";
            const entryType = normalizeEntryType(row);
            const timestamp = toTimestamp(row.timestamp);
            const previousRow = rows[index - 1];
            const isContinued =
              Boolean(previousRow) &&
              String(previousRow?.from_agent || "")
                .trim()
                .toLowerCase() === from.toLowerCase() &&
              timestamp - toTimestamp(previousRow?.timestamp) <= 90_000;
            return (
              <article
                key={`${from}-${to}-${toTimestamp(row.timestamp)}-${index}`}
                className={`flex items-start gap-2 ${isContinued ? "pt-0.5" : "pt-1.5"}`}
              >
                <div className="w-7 shrink-0 pt-0.5">
                  {!isContinued ? (
                    <span
                      className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-white/70 text-[10px] font-semibold text-[#1f2937]"
                      style={{ backgroundColor: avatarSeed(from) }}
                    >
                      {initials(from)}
                    </span>
                  ) : null}
                </div>

                <div className="min-w-0 flex-1">
                  {!isContinued ? (
                    <div className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="text-[12px] font-semibold text-[#111827]">{from}</span>
                      <span className="rounded-full border border-black/[0.08] bg-white px-2 py-0.5 text-[10px] font-semibold text-[#667085]">
                        {routeLabel(from, to)}
                      </span>
                      <span className="text-[10px] font-medium text-[#98a2b3]">
                        {new Date(timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                  ) : null}

                  <div
                    className={`max-w-[95%] rounded-2xl border px-3 py-2 shadow-[0_1px_0_rgba(17,24,39,0.02)] ${bubbleClass(
                      entryType,
                      from,
                    )}`}
                  >
                    <p className="text-[12px] leading-[1.5] text-[#1f2937]">{message}</p>
                    <div className="mt-1.5 flex items-center justify-between gap-2">
                      <span className="rounded-full border border-black/[0.08] bg-white/85 px-2 py-0.5 text-[10px] font-semibold text-[#667085]">
                        {badgeLabel(row, entryType)}
                      </span>
                      {isContinued ? (
                        <span className="text-[10px] font-medium text-[#98a2b3]">
                          {new Date(timestamp).toLocaleTimeString()}
                        </span>
                      ) : null}
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}

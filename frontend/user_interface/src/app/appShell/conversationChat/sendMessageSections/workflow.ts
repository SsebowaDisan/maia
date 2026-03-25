import type { WorkflowRunEvent } from "../../../../api/client";
import type { AgentActivityEvent } from "../../../types";
import { asRecord, normalizeModeValue } from "./common";

function deriveWorkflowEventData(row: Record<string, unknown>, data: Record<string, unknown>): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...data };
  const fallbackKeys = [
    "url",
    "source_url",
    "target_url",
    "page_url",
    "final_url",
    "link",
    "tool_id",
    "scene_surface",
    "scene_family",
    "brand_slug",
    "connector_id",
    "connector_label",
    "from_agent",
    "to_agent",
    "from_role",
    "to_role",
    "next_role",
    "agent_id",
    "agent_role",
    "owner_role",
    "step_id",
    "message",
    "question",
    "answer",
    "summary",
    "progress",
    "run_id",
  ] as const;
  for (const key of fallbackKeys) {
    if (merged[key] !== undefined) {
      continue;
    }
    if (row[key] !== undefined) {
      merged[key] = row[key];
    }
  }
  return merged;
}

function workflowEventTitle(eventType: string): string {
  const normalized = String(eventType || "")
    .trim()
    .replace(/[._-]+/g, " ")
    .toLowerCase();
  if (!normalized) {
    return "Activity";
  }
  return normalized.replace(/\b\w/g, (char) => char.toUpperCase());
}

function toActivityEventFromWorkflowEvent(
  event: WorkflowRunEvent,
  options: { fallbackRunId: string; index: number },
): AgentActivityEvent | null {
  const { fallbackRunId, index } = options;
  const row = asRecord(event);
  const data = asRecord(row.data);
  const metadata = asRecord(row.metadata);
  const resolvedData = deriveWorkflowEventData(row, data);
  const explicitEventType = normalizeModeValue(row.event_type, "").toLowerCase();
  const fallbackEventType = normalizeModeValue(
    row.type || data.type || metadata.type || metadata.event_type,
    "",
  ).toLowerCase();
  const eventType =
    explicitEventType && explicitEventType !== "event"
      ? explicitEventType
      : fallbackEventType || explicitEventType;
  if (!eventType || eventType === "done") {
    return null;
  }
  const runId = String(row.run_id || resolvedData.run_id || data.run_id || fallbackRunId).trim();
  if (!runId) {
    return null;
  }
  const title = String(row.title || "").trim() || workflowEventTitle(eventType);
  const detail = String(
    row.detail ||
      row.error ||
      row.message ||
      row.text ||
      row.delta ||
      data.detail ||
      data.error ||
      data.message ||
      data.text ||
      data.delta ||
      "",
  ).trim();
  const eventId = String(row.event_id || "").trim() || `${runId}-${eventType}-${index}`;
  const eventFamily =
    eventType.startsWith("assembly_") ||
    eventType.startsWith("brain_") ||
    eventType.startsWith("agent_dialogue")
      ? "plan"
      : eventType.startsWith("workflow_") || eventType.startsWith("execution_")
        ? "workflow"
        : undefined;
  return {
    event_id: eventId,
    run_id: runId,
    event_type: eventType,
    title,
    detail,
    timestamp: new Date().toISOString(),
    stage: eventFamily === "plan" ? "plan" : "execute",
    status: eventType.includes("error") || eventType.includes("failed") ? "failed" : "info",
    data: resolvedData,
    metadata,
    event_family: eventFamily,
    event_render_mode: eventFamily === "plan" ? "animate_live" : undefined,
  };
}

function summarizeBrainRun(events: AgentActivityEvent[]): string {
  const latestError = [...events]
    .reverse()
    .find((event) =>
      ["assembly_error", "execution_error", "workflow_failed", "error"].includes(
        String(event.event_type || "").trim().toLowerCase(),
      ),
    );
  if (latestError) {
    return latestError.detail
      ? `Brain run failed: ${latestError.detail}`
      : `Brain run failed at ${latestError.title}.`;
  }

  const executionComplete = [...events].reverse().find((event) => {
    const type = String(event.event_type || "").trim().toLowerCase();
    return type === "execution_complete" || type === "workflow_completed";
  });
  const outputRecord = asRecord(executionComplete?.data?.outputs);
  const deliverySentEvent = [...events]
    .reverse()
    .find((event) => String(event.event_type || "").trim().toLowerCase() === "email_sent");
  const rankedOutputs = Object.entries(outputRecord)
    .map(([key, value]) => {
      const preview = String(value || "").replace(/\r\n/g, "\n").trim();
      let score = 0;
      if (preview.includes("## Evidence Citations")) {
        score += 5;
      }
      if (/\[\d+\]/.test(preview)) {
        score += 3;
      }
      if (/##\s+(executive summary|key findings|summary|findings)/i.test(preview)) {
        score += 2;
      }
      if (/email sent to|sent cited email to/i.test(preview)) {
        score -= 5;
      }
      if (/^to:\s.+\nsubject:\s/im.test(preview)) {
        score -= 2;
      }
      if (/draft|summary|research|report|findings/i.test(key)) {
        score += 2;
      }
      score += Math.min(4, Math.floor(preview.length / 700));
      return { key, preview, score };
    })
    .filter((row) => row.preview)
    .sort((left, right) => right.score - left.score);
  const citedResearchBrief = rankedOutputs.find(
    (row) =>
      /\[\d+\]/.test(row.preview) &&
      !/^subject:\s/im.test(row.preview) &&
      !/^to:\s/im.test(row.preview) &&
      /##\s+(executive summary|key findings|summary|findings)/i.test(row.preview),
  );
  if (citedResearchBrief) {
    const recipient = String(deliverySentEvent?.data?.recipient || "").trim();
    const confirmation = recipient ? `\n\nEmail sent to ${recipient}.` : "";
    return `${citedResearchBrief.preview}${confirmation}`;
  }
  const primaryRichOutput = rankedOutputs[0]?.preview || "";
  if (primaryRichOutput && (primaryRichOutput.includes("## Evidence Citations") || /\[\d+\]/.test(primaryRichOutput))) {
    return primaryRichOutput;
  }
  const outputLines = Object.entries(outputRecord)
    .slice(0, 4)
    .map(([key, value]) => {
      const preview = String(value || "").replace(/\s+/g, " ").trim();
      if (!preview) {
        return null;
      }
      return `- ${key}: ${preview.slice(0, 220)}${preview.length > 220 ? "..." : ""}`;
    })
    .filter((line): line is string => Boolean(line));

  const workflowSaved = [...events]
    .reverse()
    .find((event) => String(event.event_type || "").trim().toLowerCase() === "workflow_saved");
  const workflowId = String(workflowSaved?.data?.workflow_id || "").trim();

  if (outputLines.length) {
    return [
      "Brain assembled and executed the workflow successfully.",
      "",
      "Results:",
      ...outputLines,
      workflowId ? "" : "",
      workflowId ? `Workflow ID: ${workflowId}` : "",
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (workflowId) {
    return `Brain assembled and executed the workflow successfully (workflow ${workflowId}).`;
  }
  return "Brain assembled and executed the workflow successfully.";
}

export { summarizeBrainRun, toActivityEventFromWorkflowEvent };

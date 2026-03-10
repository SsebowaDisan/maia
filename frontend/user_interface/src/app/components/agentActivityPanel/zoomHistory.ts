import type { AgentActivityEvent } from "../../types";

type ZoomHistoryEntry = {
  eventRef: string;
  eventType: string;
  eventIndex: number | null;
  timestamp: string;
  action: "zoom_in" | "zoom_out" | "zoom_reset" | "zoom_to_region";
  sceneSurface: string;
  sceneRef: string;
  graphNodeId: string;
  zoomLevel: number | null;
  zoomReason: string;
  zoomPolicyTriggers: string[];
};

const ZOOM_ACTIONS = new Set(["zoom_in", "zoom_out", "zoom_reset", "zoom_to_region"]);

function cleanText(value: unknown): string {
  return String(value || "").trim();
}

function normalizedText(value: unknown): string {
  return cleanText(value).toLowerCase();
}

function asNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const cleaned = value
    .map((item) => cleanText(item))
    .filter((item) => item.length > 0);
  return Array.from(new Set(cleaned));
}

function zoomActionFromEvent(eventType: string, payload: Record<string, unknown>): string {
  const action = normalizedText(payload.action);
  if (ZOOM_ACTIONS.has(action)) {
    return action;
  }
  const normalizedEvent = normalizedText(eventType).replace("-", "_");
  if (normalizedEvent.includes("zoom_to_region")) {
    return "zoom_to_region";
  }
  if (normalizedEvent.includes("zoom_in")) {
    return "zoom_in";
  }
  if (normalizedEvent.includes("zoom_out")) {
    return "zoom_out";
  }
  if (normalizedEvent.includes("zoom_reset")) {
    return "zoom_reset";
  }
  return "";
}

function readReferenceList(payload: Record<string, unknown>, pluralKey: string, singularKey: string): string[] {
  const fromPlural = stringList(payload[pluralKey]);
  if (fromPlural.length) {
    return fromPlural;
  }
  const singular = cleanText(payload[singularKey]);
  return singular ? [singular] : [];
}

function extractZoomHistoryEntry(event: AgentActivityEvent, payload: Record<string, unknown>): ZoomHistoryEntry | null {
  const embedded =
    payload.zoom_event && typeof payload.zoom_event === "object"
      ? (payload.zoom_event as Record<string, unknown>)
      : null;
  const source = embedded || payload;
  const action = zoomActionFromEvent(String(source.event_type || event.event_type || ""), source);
  if (!ZOOM_ACTIONS.has(action)) {
    return null;
  }
  const eventRef = cleanText(source.event_ref || event.event_id);
  const eventType = cleanText(source.event_type || event.event_type);
  const eventIndexRaw = asNumber(source.event_index ?? event.event_index ?? event.seq);
  const eventIndex = eventIndexRaw !== null && eventIndexRaw > 0 ? Math.round(eventIndexRaw) : null;
  const timestamp = cleanText(source.timestamp || event.timestamp || event.ts);
  const sceneSurface = cleanText(source.scene_surface || payload.scene_surface);
  const sceneRef = cleanText(source.scene_ref || payload.scene_ref);
  const graphNodeId = cleanText(source.graph_node_id || payload.graph_node_id);
  const zoomLevelRaw = asNumber(source.zoom_level ?? source.zoom_to ?? payload.zoom_level ?? payload.zoom_to);
  const zoomLevel = zoomLevelRaw !== null && zoomLevelRaw > 0 ? Number(zoomLevelRaw.toFixed(3)) : null;
  const zoomReason = cleanText(source.zoom_reason || payload.zoom_reason || payload.reason);
  const zoomPolicyTriggers = stringList(source.zoom_policy_triggers || payload.zoom_policy_triggers);

  return {
    eventRef,
    eventType,
    eventIndex,
    timestamp,
    action: action as ZoomHistoryEntry["action"],
    sceneSurface,
    sceneRef,
    graphNodeId,
    zoomLevel,
    zoomReason,
    zoomPolicyTriggers,
  };
}

function appendZoomHistory(
  history: ZoomHistoryEntry[],
  event: AgentActivityEvent,
  payload: Record<string, unknown>,
): ZoomHistoryEntry[] {
  const next = [...history];
  const entry = extractZoomHistoryEntry(event, payload);
  if (entry) {
    const normalizedRef = normalizedText(entry.eventRef);
    const existingIndex =
      normalizedRef.length > 0
        ? next.findIndex((item) => normalizedText(item.eventRef) === normalizedRef)
        : -1;
    if (existingIndex >= 0) {
      next[existingIndex] = entry;
    } else {
      next.push(entry);
    }
  }
  return next;
}

function collectReferenceTokens(
  event: AgentActivityEvent,
  payload: Record<string, unknown>,
): {
  graphNodeIds: string[];
  sceneRefs: string[];
  eventRefs: string[];
} {
  const graphNodeIds = readReferenceList(payload, "graph_node_ids", "graph_node_id");
  const sceneRefs = readReferenceList(payload, "scene_refs", "scene_ref");
  const eventRefs = readReferenceList(payload, "event_refs", "event_id");
  const eventId = cleanText(event.event_id);
  if (eventId && !eventRefs.includes(eventId)) {
    eventRefs.push(eventId);
  }
  return { graphNodeIds, sceneRefs, eventRefs };
}

export type { ZoomHistoryEntry };
export { appendZoomHistory, collectReferenceTokens };

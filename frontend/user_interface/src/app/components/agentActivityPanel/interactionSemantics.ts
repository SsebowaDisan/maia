import type { AgentActivityEvent } from "../../types";
import { eventMetadataString, tabForEventType } from "../agentActivityMeta";
import type { PreviewTab } from "../agentActivityMeta";
import { readNumberField, readStringField } from "./helpers";

const SURFACE_TO_TAB: Record<string, PreviewTab> = {
  browser: "browser",
  website: "browser",
  web: "browser",
  preview: "browser",
  maps: "browser",
  document: "document",
  google_docs: "document",
  google_sheets: "document",
  docs: "document",
  sheets: "document",
  email: "email",
  gmail: "email",
  api: "system",
  system: "system",
  workspace: "system",
};

const ROLE_LABELS: Record<string, string> = {
  conductor: "Conductor",
  planner: "Planner",
  research: "Research",
  browser: "Browser",
  writer: "Writer",
  verifier: "Verifier",
  safety: "Safety",
  document_reader: "Document",
  analyst: "Analyst",
  chart_builder: "Analyst",
  workspace_editor: "Writer",
  goal_page_discovery: "Browser",
  contact_form: "Browser",
  system: "System",
};

const ROLE_COLORS: Record<string, string> = {
  conductor: "#2563eb",
  planner: "#7c3aed",
  research: "#0ea5e9",
  browser: "#0284c7",
  writer: "#7c2d12",
  verifier: "#15803d",
  safety: "#dc2626",
  document_reader: "#475569",
  analyst: "#1d4ed8",
  chart_builder: "#1d4ed8",
  workspace_editor: "#9333ea",
  goal_page_discovery: "#0369a1",
  contact_form: "#0369a1",
  system: "#6b7280",
};

const ACTIONS = new Set([
  "navigate",
  "hover",
  "click",
  "type",
  "scroll",
  "zoom_in",
  "zoom_out",
  "zoom_reset",
  "zoom_to_region",
  "extract",
  "verify",
  "other",
]);

function normalizeToken(value: string): string {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_");
}

function toTitleFromSnake(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function tabForSceneSurface(surface: string): PreviewTab | null {
  const normalized = normalizeToken(surface);
  if (!normalized) {
    return null;
  }
  return SURFACE_TO_TAB[normalized] || null;
}

function eventTab(event: AgentActivityEvent | null): PreviewTab {
  if (!event) {
    return "system";
  }
  const isShadowStep =
    String(event.event_type || "").toLowerCase() === "tool_completed" &&
    String(event.data?.["shadow"] ?? event.metadata?.["shadow"] ?? "")
      .trim()
      .toLowerCase() === "true";
  if (isShadowStep) {
    return "system";
  }
  const interactionSurface = sceneSurfaceFromEvent(event);
  const surfaceTab = tabForSceneSurface(interactionSurface);
  if (surfaceTab) {
    return surfaceTab;
  }
  const byType = tabForEventType(event.event_type || "");
  if (byType !== "system") {
    return byType;
  }
  const toolId = eventMetadataString(event, "tool_id") || readStringField(event.data?.["tool_id"]);
  if (toolId.startsWith("workspace.docs.") || toolId.startsWith("workspace.sheets.")) {
    return "document";
  }
  if (toolId.startsWith("browser.") || toolId.startsWith("marketing.web_research")) {
    return "browser";
  }
  return "system";
}

function isApiRuntimeEvent(event: AgentActivityEvent | null): boolean {
  if (!event) {
    return false;
  }
  const sceneSurface = sceneSurfaceFromEvent(event).toLowerCase();
  if (sceneSurface === "api") {
    return true;
  }
  const eventFamily =
    readStringField(event.data?.["event_family"]) ||
    readStringField(event.metadata?.["event_family"]) ||
    "";
  if (eventFamily.trim().toLowerCase() === "api") {
    return true;
  }
  const eventType = readStringField(event.event_type).trim().toLowerCase();
  return eventType.startsWith("api_") || eventType.startsWith("api.");
}

function sceneSurfaceFromEvent(event: AgentActivityEvent | null): string {
  if (!event) {
    return "";
  }
  return (
    eventMetadataString(event, "scene_surface") ||
    readStringField(event.data?.["scene_surface"]) ||
    ""
  );
}

function cursorFromEvent(event: AgentActivityEvent | null): { x: number; y: number } | null {
  if (!event) {
    return null;
  }
  const dataX = readNumberField(event.data?.["cursor_x"]);
  const dataY = readNumberField(event.data?.["cursor_y"]);
  const metaX = readNumberField(event.metadata?.["cursor_x"]);
  const metaY = readNumberField(event.metadata?.["cursor_y"]);
  const x = dataX ?? metaX;
  const y = dataY ?? metaY;
  if (x === null || y === null) {
    return null;
  }
  return {
    x: Math.max(2, Math.min(98, x)),
    y: Math.max(2, Math.min(98, y)),
  };
}

function roleKeyFromEvent(event: AgentActivityEvent | null): string {
  if (!event) {
    return "";
  }
  const candidate =
    readStringField(event.data?.["owner_role"]) ||
    readStringField(event.metadata?.["owner_role"]) ||
    readStringField(event.data?.["__owner_role"]) ||
    readStringField(event.metadata?.["__owner_role"]) ||
    readStringField(event.data?.["role"]) ||
    readStringField(event.metadata?.["role"]) ||
    readStringField(event.data?.["to_role"]) ||
    readStringField(event.metadata?.["to_role"]) ||
    readStringField(event.data?.["agent_role"]) ||
    readStringField(event.metadata?.["agent_role"]);
  return normalizeToken(candidate);
}

function roleLabelFromKey(roleKey: string): string {
  const normalized = normalizeToken(roleKey);
  if (!normalized) {
    return "";
  }
  return ROLE_LABELS[normalized] || toTitleFromSnake(normalized);
}

function roleColorFromKey(roleKey: string): string {
  const normalized = normalizeToken(roleKey);
  if (!normalized) {
    return ROLE_COLORS.system;
  }
  return ROLE_COLORS[normalized] || ROLE_COLORS.system;
}

function agentLabelFromEvent(event: AgentActivityEvent | null): string {
  if (!event) {
    return "";
  }
  const explicitLabel =
    readStringField(event.data?.["agent_label"]) ||
    readStringField(event.metadata?.["agent_label"]);
  if (explicitLabel) {
    return explicitLabel;
  }
  return roleLabelFromKey(roleKeyFromEvent(event));
}

function agentColorFromEvent(event: AgentActivityEvent | null): string {
  if (!event) {
    return ROLE_COLORS.system;
  }
  const explicitColor =
    readStringField(event.data?.["agent_color"]) ||
    readStringField(event.metadata?.["agent_color"]);
  if (explicitColor) {
    return explicitColor;
  }
  return roleColorFromKey(roleKeyFromEvent(event));
}

function agentEventTypeFromEvent(event: AgentActivityEvent | null): string {
  if (!event) {
    return "";
  }
  return (
    readStringField(event.data?.["agent_event_type"]) ||
    readStringField(event.metadata?.["agent_event_type"]) ||
    readStringField(event.event_type)
  )
    .trim()
    .toLowerCase();
}

function interactionActionFromEvent(event: AgentActivityEvent | null): string {
  if (!event) {
    return "";
  }
  const candidate =
    readStringField(event.data?.["action"]) ||
    readStringField(event.metadata?.["action"]) ||
    "";
  const normalized = normalizeToken(candidate);
  return ACTIONS.has(normalized) ? normalized : "";
}

function interactionActionPhaseFromEvent(event: AgentActivityEvent | null): string {
  if (!event) {
    return "";
  }
  return normalizeToken(
    readStringField(event.data?.["action_phase"]) || readStringField(event.metadata?.["action_phase"]),
  );
}

function interactionActionStatusFromEvent(event: AgentActivityEvent | null): string {
  if (!event) {
    return "";
  }
  return normalizeToken(
    readStringField(event.data?.["action_status"]) ||
      readStringField(event.metadata?.["action_status"]) ||
      readStringField(event.status),
  );
}

function surfaceLabelForSceneKey(sceneSurfaceKey: string): string {
  const key = normalizeToken(sceneSurfaceKey);
  if (key === "website") return "Website";
  if (key === "google_sheets") return "Google Sheets";
  if (key === "google_docs") return "Google Docs";
  if (key === "document") return "Document";
  if (key === "email") return "Email";
  if (key === "api") return "API";
  if (key === "workspace") return "Workspace";
  return "System";
}

function cursorLabelFromSemantics(args: {
  action: string;
  actionStatus: string;
  actionPhase: string;
  sceneSurfaceLabel: string;
  roleLabel: string;
  agentEventType?: string;
}): string {
  const action = normalizeToken(args.action);
  const status = normalizeToken(args.actionStatus);
  const phase = normalizeToken(args.actionPhase);
  const roleLabel = String(args.roleLabel || "").trim();
  const agentEventType = String(args.agentEventType || "").trim().toLowerCase();
  const subject = roleLabel || "Agent";
  const surfaceLabel = String(args.sceneSurfaceLabel || "workspace").trim().toLowerCase();
  if (agentEventType === "agent.waiting") {
    return `${subject} awaiting confirmation`;
  }
  if (agentEventType === "agent.blocked") {
    return `${subject} blocked`;
  }
  if (agentEventType === "agent.handoff") {
    return `${subject} handing off`;
  }
  if (agentEventType === "agent.resume") {
    return `${subject} resumed`;
  }
  if (status === "failed") {
    return `${subject} retrying`;
  }
  if (action === "navigate") {
    return `${subject} opening ${surfaceLabel}`;
  }
  if (action === "click") {
    return `${subject} selecting target`;
  }
  if (action === "type") {
    return `${subject} typing`;
  }
  if (action === "scroll") {
    return `${subject} scanning`;
  }
  if (action === "zoom_in") {
    return `${subject} zooming in`;
  }
  if (action === "zoom_out") {
    return `${subject} zooming out`;
  }
  if (action === "zoom_reset") {
    return `${subject} resetting zoom`;
  }
  if (action === "zoom_to_region") {
    return `${subject} inspecting detail`;
  }
  if (action === "extract") {
    return `${subject} gathering evidence`;
  }
  if (action === "verify") {
    return `${subject} verifying`;
  }
  if (phase === "start" || phase === "active") {
    return `${subject} working`;
  }
  return `${subject} active`;
}

function roleNarrativeFromSemantics(args: {
  roleLabel: string;
  action: string;
  sceneSurfaceLabel: string;
  fallback: string;
  agentEventType?: string;
}): string {
  const roleLabel = String(args.roleLabel || "").trim() || "Agent";
  const action = normalizeToken(args.action);
  const surface = String(args.sceneSurfaceLabel || "workspace").trim().toLowerCase();
  const agentEventType = String(args.agentEventType || "").trim().toLowerCase();
  if (agentEventType === "agent.handoff") return `${roleLabel} is handing control to the next specialist.`;
  if (agentEventType === "agent.waiting") return `${roleLabel} is waiting for human verification.`;
  if (agentEventType === "agent.blocked") return `${roleLabel} is blocked by a policy or verification rule.`;
  if (agentEventType === "agent.resume") return `${roleLabel} resumed execution.`;
  if (action === "navigate") return `${roleLabel} is opening ${surface}.`;
  if (action === "click") return `${roleLabel} is selecting a target in ${surface}.`;
  if (action === "type") return `${roleLabel} is composing output in ${surface}.`;
  if (action === "scroll") return `${roleLabel} is scanning ${surface}.`;
  if (action === "zoom_in") return `${roleLabel} is zooming in on ${surface}.`;
  if (action === "zoom_out") return `${roleLabel} is zooming out in ${surface}.`;
  if (action === "zoom_reset") return `${roleLabel} is resetting zoom in ${surface}.`;
  if (action === "zoom_to_region") return `${roleLabel} is zooming to a focus region in ${surface}.`;
  if (action === "extract") return `${roleLabel} is gathering evidence from ${surface}.`;
  if (action === "verify") return `${roleLabel} is verifying completion in ${surface}.`;
  return `${roleLabel} is ${String(args.fallback || "working").trim().toLowerCase()}.`;
}

export {
  agentColorFromEvent,
  agentEventTypeFromEvent,
  agentLabelFromEvent,
  cursorFromEvent,
  cursorLabelFromSemantics,
  eventTab,
  isApiRuntimeEvent,
  interactionActionFromEvent,
  interactionActionPhaseFromEvent,
  interactionActionStatusFromEvent,
  roleColorFromKey,
  roleKeyFromEvent,
  roleLabelFromKey,
  roleNarrativeFromSemantics,
  sceneSurfaceFromEvent,
  surfaceLabelForSceneKey,
  tabForSceneSurface,
};

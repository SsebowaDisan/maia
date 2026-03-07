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

const ACTIONS = new Set(["navigate", "hover", "click", "type", "scroll", "extract", "verify", "other"]);

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
  if (key === "workspace") return "Workspace";
  return "System";
}

function cursorLabelFromSemantics(args: {
  action: string;
  actionStatus: string;
  actionPhase: string;
  sceneSurfaceLabel: string;
  roleLabel: string;
}): string {
  const action = normalizeToken(args.action);
  const status = normalizeToken(args.actionStatus);
  const phase = normalizeToken(args.actionPhase);
  const roleLabel = String(args.roleLabel || "").trim();
  const subject = roleLabel || "Agent";
  const surfaceLabel = String(args.sceneSurfaceLabel || "workspace").trim().toLowerCase();
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
}): string {
  const roleLabel = String(args.roleLabel || "").trim() || "Agent";
  const action = normalizeToken(args.action);
  const surface = String(args.sceneSurfaceLabel || "workspace").trim().toLowerCase();
  if (action === "navigate") return `${roleLabel} is opening ${surface}.`;
  if (action === "click") return `${roleLabel} is selecting a target in ${surface}.`;
  if (action === "type") return `${roleLabel} is composing output in ${surface}.`;
  if (action === "scroll") return `${roleLabel} is scanning ${surface}.`;
  if (action === "extract") return `${roleLabel} is gathering evidence from ${surface}.`;
  if (action === "verify") return `${roleLabel} is verifying completion in ${surface}.`;
  return `${roleLabel} is ${String(args.fallback || "working").trim().toLowerCase()}.`;
}

export {
  cursorFromEvent,
  cursorLabelFromSemantics,
  eventTab,
  interactionActionFromEvent,
  interactionActionPhaseFromEvent,
  interactionActionStatusFromEvent,
  roleKeyFromEvent,
  roleLabelFromKey,
  roleNarrativeFromSemantics,
  sceneSurfaceFromEvent,
  surfaceLabelForSceneKey,
  tabForSceneSurface,
};

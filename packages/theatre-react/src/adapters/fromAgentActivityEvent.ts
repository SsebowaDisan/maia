import type {
  ACPActivity,
  ACPExecutionActivity,
  ACPExecutionEvent,
  ExecutionBrowserState,
  ExecutionDocumentState,
  ExecutionEmailState,
  ExecutionExtension,
  ExecutionSurface,
} from "@maia/acp";
import { executionActivity, executionEnvelope } from "@maia/acp";

interface AgentActivityEventLike {
  event_id: string;
  run_id: string;
  seq?: number;
  ts?: string;
  stage?: string;
  status?: string;
  event_type: string;
  title: string;
  detail: string;
  timestamp: string;
  data?: Record<string, unknown>;
  event_family?: string;
  event_render_mode?: string;
  event_replay_importance?: string;
  replay_importance?: string;
  event_index?: number;
  graph_node_id?: string | null;
  scene_ref?: string | null;
  snapshot_ref?: string | null;
  metadata?: Record<string, unknown>;
}

type BrowserAction = "navigate" | "click" | "type" | "scroll" | "extract";

function readString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

function readNumber(...values: unknown[]): number | null {
  for (const value of values) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function detectSurface(event: AgentActivityEventLike): ExecutionSurface | "unknown" {
  const data = event.data ?? {};
  const metadata = event.metadata ?? {};
  const direct = readString(
    data["scene_surface"],
    metadata["scene_surface"],
  ).toLowerCase();
  if (direct) {
    return direct as ExecutionSurface;
  }

  const eventType = String(event.event_type || "").trim().toLowerCase();
  if (
    eventType.startsWith("browser_") ||
    eventType.startsWith("web_") ||
    eventType.startsWith("computer_use_")
  ) {
    return "browser";
  }
  if (eventType.startsWith("email_")) {
    return "email";
  }
  if (eventType.startsWith("sheet_") || eventType.startsWith("sheets.")) {
    return "sheets";
  }
  if (eventType.startsWith("doc_") || eventType.startsWith("docs.")) {
    return "document";
  }
  if (eventType.startsWith("pdf_")) {
    return "pdf";
  }
  if (eventType.startsWith("api_")) {
    return "api";
  }
  return "unknown";
}

function inferActivityType(event: AgentActivityEventLike, surface: ExecutionSurface | "unknown"): ACPActivity["activity"] {
  const status = String(event.status || "").trim().toLowerCase();
  const stage = String(event.stage || "").trim().toLowerCase();
  const eventType = String(event.event_type || "").trim().toLowerCase();

  if (status === "failed" || status === "error" || eventType.includes("error")) {
    return "error";
  }
  if (surface === "browser") {
    return "browsing";
  }
  if (surface === "email" || surface === "docs" || surface === "sheets") {
    return "writing";
  }
  if (surface === "document" || surface === "pdf") {
    return "reading";
  }
  if (
    eventType.includes("tool") ||
    readString(event.data?.["tool_id"], event.data?.["tool_name"], event.metadata?.["tool_id"], event.metadata?.["tool_name"])
  ) {
    return "tool_calling";
  }
  if (stage === "review" || eventType.includes("review") || eventType.includes("verify")) {
    return "reviewing";
  }
  if (stage === "understand" || stage === "breakdown") {
    return "thinking";
  }
  return "analyzing";
}

function deriveToolActivity(event: AgentActivityEventLike): ACPActivity["tool"] | undefined {
  const data = event.data ?? {};
  const metadata = event.metadata ?? {};
  const toolId = readString(data["tool_id"], metadata["tool_id"]);
  const toolName = readString(data["tool_name"], metadata["tool_name"]);
  const connectorId = readString(data["connector_id"], metadata["connector_id"]);
  if (!toolId && !toolName && !connectorId) {
    return undefined;
  }
  const normalizedStatus = String(event.status || "").trim().toLowerCase();
  const status =
    normalizedStatus === "failed"
      ? "failed"
      : normalizedStatus === "completed" || normalizedStatus === "success"
        ? "completed"
        : normalizedStatus === "running"
          ? "running"
          : "started";
  return {
    tool_id: toolId || toolName || "tool",
    tool_name: toolName || undefined,
    connector_id: connectorId || undefined,
    input_summary: readString(data["input_summary"], metadata["input_summary"]) || undefined,
    output_summary: readString(data["output_summary"], metadata["output_summary"]) || undefined,
    status,
  };
}

function deriveBrowserState(event: AgentActivityEventLike, surface: ExecutionSurface | "unknown"): ExecutionBrowserState | undefined {
  if (surface !== "browser" && surface !== "pdf") {
    return undefined;
  }
  const data = event.data ?? {};
  const metadata = event.metadata ?? {};
  const url = readString(
    data["url"],
    data["browser_url"],
    data["page_url"],
    data["source_url"],
    metadata["url"],
    metadata["browser_url"],
  );
  return {
    url: url || undefined,
    title: readString(data["title"], metadata["title"]) || undefined,
    action: readString(data["action"], metadata["action"]) || undefined,
    computer_use_session_id: readString(data["computer_use_session_id"], metadata["computer_use_session_id"]) || undefined,
    computer_use_task: readString(data["computer_use_task"], metadata["computer_use_task"]) || undefined,
    computer_use_model: readString(data["computer_use_model"], metadata["computer_use_model"]) || undefined,
    computer_use_max_iterations: readNumber(data["computer_use_max_iterations"], metadata["computer_use_max_iterations"]),
    screenshot_url: readString(data["screenshot_url"], metadata["screenshot_url"], data["snapshot_url"], metadata["snapshot_url"]) || undefined,
    screenshot_b64: readString(data["screenshot_b64"], metadata["screenshot_b64"]) || undefined,
    cursor_x: readNumber(data["cursor_x"], metadata["cursor_x"]),
    cursor_y: readNumber(data["cursor_y"], metadata["cursor_y"]),
    scroll_percent: readNumber(data["scroll_percent"], metadata["scroll_percent"]),
    zoom_level: readNumber(data["zoom_level"], metadata["zoom_level"]),
    page_index: readNumber(data["page_index"], metadata["page_index"]),
    narration: readString(data["narration"], metadata["narration"]) || undefined,
  };
}

function normalizeBrowserAction(value: string): BrowserAction | undefined {
  switch (value) {
    case "navigate":
    case "click":
    case "type":
    case "scroll":
    case "extract":
      return value;
    default:
      return undefined;
  }
}

function deriveEmailState(event: AgentActivityEventLike, surface: ExecutionSurface | "unknown"): ExecutionEmailState | undefined {
  if (surface !== "email") {
    return undefined;
  }
  const data = event.data ?? {};
  const metadata = event.metadata ?? {};
  return {
    recipient: readString(data["email_recipient"], metadata["email_recipient"], data["recipient"], metadata["recipient"]) || undefined,
    subject: readString(data["email_subject"], metadata["email_subject"], data["subject"], metadata["subject"]) || undefined,
    body_preview: readString(data["body_preview"], metadata["body_preview"], data["content"], metadata["content"]) || undefined,
  };
}

function deriveDocumentState(event: AgentActivityEventLike, surface: ExecutionSurface | "unknown"): ExecutionDocumentState | undefined {
  if (surface === "unknown" || surface === "browser" || surface === "email" || surface === "api" || surface === "system" || surface === "chat") {
    return undefined;
  }
  const data = event.data ?? {};
  const metadata = event.metadata ?? {};
  return {
    document_url: readString(data["document_url"], metadata["document_url"], data["url"], metadata["url"]) || undefined,
    spreadsheet_url: readString(data["spreadsheet_url"], metadata["spreadsheet_url"]) || undefined,
    body_preview: readString(data["body_preview"], metadata["body_preview"], data["content"], metadata["content"]) || undefined,
    content_before: readString(data["content_before"], metadata["content_before"]) || undefined,
    content_after: readString(data["content_after"], metadata["content_after"]) || undefined,
  };
}

function deriveAgentId(event: AgentActivityEventLike): string {
  const data = event.data ?? {};
  const metadata = event.metadata ?? {};
  const raw = readString(
    data["agent_id"],
    metadata["agent_id"],
    metadata["role_key"],
    metadata["role"],
    data["role_key"],
    data["role"],
  );
  if (!raw) {
    return "agent://maia";
  }
  return raw.startsWith("agent://") ? raw : `agent://${raw}`;
}

function toExecutionExtension(event: AgentActivityEventLike): ExecutionExtension {
  const data = event.data ?? {};
  const metadata = event.metadata ?? {};
  const surface = detectSurface(event);
  return {
    stage: event.stage || undefined,
    status: event.status || undefined,
    title: event.title,
    detail: event.detail,
    scene_surface: surface === "unknown" ? undefined : surface,
    scene_family: readString(data["scene_family"], metadata["scene_family"]) || undefined,
    ui_target: readString(data["ui_target"], metadata["ui_target"]) || undefined,
    event_index: event.event_index ?? event.seq,
    render_mode: event.event_render_mode || undefined,
    replay_importance: event.event_replay_importance || event.replay_importance || undefined,
    scene_ref: event.scene_ref,
    snapshot_ref: event.snapshot_ref,
    graph_node_id: event.graph_node_id,
    metadata,
    raw_data: data,
    raw_metadata: metadata,
    browser_state: deriveBrowserState(event, surface),
    email_state: deriveEmailState(event, surface),
    document_state: deriveDocumentState(event, surface),
  };
}

function fromAgentActivityEvent(event: AgentActivityEventLike): ACPExecutionEvent {
  const surface = detectSurface(event);
  const agentId = deriveAgentId(event);
  const detail = readString(event.detail, event.title) || "Agent activity update.";
  const browserState = deriveBrowserState(event, surface);
  const tool = deriveToolActivity(event);
  const payload: ACPExecutionActivity = executionActivity({
    agentId,
    activity: inferActivityType(event, surface),
    detail,
    tool,
    browser: browserState?.url
        ? {
            url: browserState.url,
            title: browserState.title,
            screenshot_url: browserState.screenshot_url,
            action: normalizeBrowserAction(String(browserState.action || "")),
          }
        : undefined,
    execution: toExecutionExtension(event),
  });
  const wrapped = executionEnvelope(agentId, event.run_id, payload, event.event_id);
  return {
    ...wrapped,
    sequence: event.seq ?? event.event_index ?? wrapped.sequence,
    timestamp: readString(event.timestamp, event.ts) || wrapped.timestamp,
  };
}

function fromAgentActivityEvents(events: AgentActivityEventLike[]): ACPExecutionEvent[] {
  return events.map((event) => fromAgentActivityEvent(event));
}

export { fromAgentActivityEvent, fromAgentActivityEvents };
export type { AgentActivityEventLike };

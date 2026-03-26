import type { ACPActivity, ACPEvent } from "./types";

type ExecutionStage =
  | "idle"
  | "understand"
  | "breakdown"
  | "analyze"
  | "surface"
  | "execute"
  | "review"
  | "confirm"
  | "done"
  | "blocked"
  | "needs_input"
  | "error";

type ExecutionStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "blocked"
  | "needs_input";

type ExecutionSurface =
  | "system"
  | "browser"
  | "email"
  | "document"
  | "docs"
  | "sheets"
  | "pdf"
  | "snapshot"
  | "api"
  | "chat";

type ExecutionSceneFamily =
  | "system"
  | "browser"
  | "document"
  | "communication"
  | "api"
  | "chat"
  | "artifact";

type ExecutionMetadata = Record<string, unknown>;

interface ExecutionBrowserState {
  url?: string;
  title?: string;
  action?: string;
  computer_use_session_id?: string;
  computer_use_task?: string;
  computer_use_model?: string;
  computer_use_max_iterations?: number | null;
  screenshot_url?: string;
  screenshot_b64?: string;
  cursor_x?: number | null;
  cursor_y?: number | null;
  scroll_percent?: number | null;
  zoom_level?: number | null;
  page_index?: number | null;
  narration?: string | null;
  [key: string]: unknown;
}

interface ExecutionEmailState {
  recipient?: string;
  subject?: string;
  body_preview?: string;
  [key: string]: unknown;
}

interface ExecutionDocumentState {
  document_url?: string;
  spreadsheet_url?: string;
  body_preview?: string;
  content_before?: string;
  content_after?: string;
  [key: string]: unknown;
}

interface ExecutionExtension {
  stage?: ExecutionStage | string;
  status?: ExecutionStatus | string;
  title?: string;
  detail?: string;
  scene_surface?: ExecutionSurface | string;
  scene_family?: ExecutionSceneFamily | string;
  ui_target?: string;
  event_index?: number;
  render_mode?: string;
  replay_importance?: string;
  scene_ref?: string | null;
  snapshot_ref?: string | null;
  graph_node_id?: string | null;
  metadata?: ExecutionMetadata;
  raw_data?: Record<string, unknown>;
  raw_metadata?: Record<string, unknown>;
  browser_state?: ExecutionBrowserState;
  email_state?: ExecutionEmailState;
  document_state?: ExecutionDocumentState;
}

interface ACPExecutionActivity extends ACPActivity {
  execution?: ExecutionExtension;
}

type ACPExecutionEvent = ACPEvent<ACPExecutionActivity>;

export type {
  ExecutionStage,
  ExecutionStatus,
  ExecutionSurface,
  ExecutionSceneFamily,
  ExecutionMetadata,
  ExecutionBrowserState,
  ExecutionEmailState,
  ExecutionDocumentState,
  ExecutionExtension,
  ACPExecutionActivity,
  ACPExecutionEvent,
};

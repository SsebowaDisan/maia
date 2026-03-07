type ConversationSummary = {
  id: string;
  name: string;
  icon_key?: string | null;
  user: string;
  is_public: boolean;
  date_created: string;
  date_updated: string;
  message_count: number;
};

type ConversationDetail = ConversationSummary & {
  data_source: {
    messages?: [string, string][];
    retrieval_messages?: string[];
    [key: string]: unknown;
  };
};

type MindmapShareResponse = {
  share_id: string;
  conversation_id: string;
  title: string;
  date_created: string;
  map: Record<string, unknown>;
};

type MindmapPayloadResponse = Record<string, unknown>;

type AgentActionRecord = {
  tool_id: string;
  action_class: "read" | "draft" | "execute";
  status: "success" | "failed" | "skipped";
  summary: string;
  started_at?: string;
  ended_at?: string;
  metadata?: Record<string, unknown>;
};

type AgentSourceRecord = {
  source_type: string;
  label: string;
  url?: string | null;
  file_id?: string | null;
  score?: number | null;
  metadata?: Record<string, unknown>;
};

type SourceUsageRecord = {
  source_id: string;
  source_name: string;
  source_type: string;
  retrieved_count: number;
  cited_count: number;
  max_strength_score: number;
  avg_strength_score: number;
  citation_share: number;
};

type AgentActivityEvent = {
  event_schema_version?: string;
  event_id: string;
  run_id: string;
  seq?: number;
  ts?: string;
  type?: string;
  stage?: string;
  status?: string;
  event_type: string;
  title: string;
  detail: string;
  timestamp: string;
  data?: Record<string, unknown>;
  event_family?: string;
  event_priority?: string;
  event_render_mode?: string;
  event_replay_importance?: string;
  replay_importance?: string;
  event_index?: number;
  graph_node_id?: string | null;
  scene_ref?: string | null;
  snapshot_ref?: string | null;
  metadata: Record<string, unknown>;
};

type ChatResponse = {
  conversation_id: string;
  conversation_name: string;
  message: string;
  answer: string;
  info: string;
  plot: Record<string, unknown> | null;
  state: Record<string, unknown>;
  mode: "ask" | "company_agent" | "deep_search";
  actions_taken: AgentActionRecord[];
  sources_used: AgentSourceRecord[];
  source_usage: SourceUsageRecord[];
  next_recommended_steps: string[];
  needs_human_review: boolean;
  human_review_notes: string | null;
  web_summary: Record<string, unknown>;
  info_panel: Record<string, unknown>;
  activity_run_id: string | null;
  mindmap: Record<string, unknown>;
};

type ChatStreamEvent =
  | { type: "chat_delta"; delta: string; text: string }
  | { type: "info_delta"; delta: string }
  | { type: "plot"; plot: Record<string, unknown> | null }
  | { type: "activity"; event: AgentActivityEvent }
  | { type: "debug"; message: string }
  | { type: string; [key: string]: unknown };

type IndexSelection = {
  mode: "all" | "select" | "disabled";
  file_ids: string[];
};

type FileRecord = {
  id: string;
  name: string;
  size: number;
  note: Record<string, unknown>;
  date_created: string;
};

type FileActionResult = {
  file_id: string;
  status: string;
  message?: string;
};

type BulkDeleteFilesResponse = {
  index_id: number;
  deleted_ids: string[];
  failed: FileActionResult[];
};

type UrlActionResult = {
  url: string;
  status: string;
  message?: string;
};

type BulkDeleteUrlsResponse = {
  index_id: number;
  deleted_ids: string[];
  deleted_urls: string[];
  failed: UrlActionResult[];
};

type FileGroupRecord = {
  id: string;
  name: string;
  file_ids: string[];
  date_created: string;
};

type FileGroupListResponse = {
  index_id: number;
  groups: FileGroupRecord[];
};

type FileGroupResponse = {
  index_id: number;
  group: FileGroupRecord;
};

type MoveFilesToGroupResponse = {
  index_id: number;
  group: FileGroupRecord;
  moved_ids: string[];
  skipped_ids: string[];
};

type DeleteFileGroupResponse = {
  index_id: number;
  group_id: string;
  status: string;
};

type UploadItem = {
  file_name: string;
  status: string;
  message?: string;
  file_id?: string;
};

type UploadResponse = {
  index_id: number;
  file_ids: string[];
  errors: string[];
  items: UploadItem[];
  debug: string[];
};

type IngestionJob = {
  id: string;
  user_id: string;
  kind: string;
  status: "queued" | "running" | "completed" | "failed" | "canceled" | string;
  index_id?: number | null;
  reindex: boolean;
  total_items: number;
  processed_items: number;
  success_count: number;
  failure_count: number;
  bytes_total?: number;
  bytes_persisted?: number;
  bytes_indexed?: number;
  items: UploadItem[];
  errors: string[];
  file_ids: string[];
  debug: string[];
  message: string;
  date_created?: string | null;
  date_updated?: string | null;
  date_started?: string | null;
  date_finished?: string | null;
};

type ConnectorCredentialRecord = {
  tenant_id: string;
  connector_id: string;
  values: Record<string, string>;
  date_updated: string;
};

type ConnectorPluginActionManifest = {
  action_id: string;
  title: string;
  description: string;
  event_family:
    | "plan"
    | "graph"
    | "scene"
    | "browser"
    | "pdf"
    | "doc"
    | "sheet"
    | "email"
    | "api"
    | "verify"
    | "approval"
    | "memory"
    | "artifact"
    | "system";
  scene_type: "system" | "browser" | "document" | "email" | "sheet" | "api";
  tool_ids: string[];
};

type ConnectorPluginEvidenceEmitter = {
  emitter_id: string;
  source_type: "web" | "pdf" | "sheet" | "email" | "api" | "document";
  fields: string[];
};

type ConnectorPluginSceneMapping = {
  scene_type: "system" | "browser" | "document" | "email" | "sheet" | "api";
  action_ids: string[];
};

type ConnectorPluginGraphMapping = {
  action_id: string;
  node_type:
    | "task"
    | "plan_step"
    | "research"
    | "browser_action"
    | "document_review"
    | "spreadsheet_analysis"
    | "email_draft"
    | "verification"
    | "approval"
    | "artifact"
    | "memory_lookup"
    | "api_operation"
    | "decision";
  edge_family: "sequential" | "dependency" | "evidence" | "verification";
};

type ConnectorPluginManifest = {
  connector_id: string;
  label: string;
  enabled: boolean;
  actions: ConnectorPluginActionManifest[];
  evidence_emitters: ConnectorPluginEvidenceEmitter[];
  scene_mapping: ConnectorPluginSceneMapping[];
  graph_mapping: ConnectorPluginGraphMapping[];
};

type GoogleOAuthStatus = {
  connected: boolean;
  scopes: string[];
  enabled_tools?: string[];
  enabled_services?: string[];
  email?: string | null;
  expires_at?: string | null;
  token_type?: string | null;
  oauth_ready?: boolean;
  oauth_missing_env?: string[];
  oauth_redirect_uri?: string | null;
  oauth_client_id_configured?: boolean;
  oauth_client_secret_configured?: boolean;
  oauth_uses_stored_credentials?: boolean;
  oauth_default_scopes?: string[];
  oauth_workspace_owner_user_id?: string | null;
  oauth_current_user_is_owner?: boolean;
  oauth_can_manage_config?: boolean;
  oauth_setup_request_pending?: boolean;
  oauth_setup_request_count?: number;
  oauth_managed_by_env?: boolean;
  oauth_selected_services?: string[];
};

type GoogleOAuthConfigStatus = {
  oauth_ready: boolean;
  oauth_missing_env: string[];
  oauth_redirect_uri: string;
  oauth_client_id_configured: boolean;
  oauth_client_secret_configured: boolean;
  oauth_uses_stored_credentials: boolean;
  oauth_default_scopes?: string[];
  oauth_workspace_owner_user_id?: string | null;
  oauth_current_user_is_owner?: boolean;
  oauth_can_manage_config?: boolean;
  oauth_setup_request_pending?: boolean;
  oauth_setup_request_count?: number;
  oauth_managed_by_env?: boolean;
};

type GoogleOAuthToolCatalogEntry = {
  id: string;
  scopes: string[];
};

type SettingsResponse = {
  values: Record<string, unknown>;
};

type AgentLiveEvent = {
  type: string;
  message: string;
  data?: Record<string, unknown>;
  run_id?: string;
  timestamp?: string;
  user_id?: string;
};

export type {
  AgentActionRecord,
  AgentActivityEvent,
  AgentLiveEvent,
  AgentSourceRecord,
  BulkDeleteFilesResponse,
  BulkDeleteUrlsResponse,
  ChatResponse,
  ChatStreamEvent,
  ConnectorCredentialRecord,
  ConnectorPluginActionManifest,
  ConnectorPluginEvidenceEmitter,
  ConnectorPluginGraphMapping,
  ConnectorPluginManifest,
  ConnectorPluginSceneMapping,
  ConversationDetail,
  ConversationSummary,
  DeleteFileGroupResponse,
  FileActionResult,
  FileGroupListResponse,
  FileGroupRecord,
  FileGroupResponse,
  FileRecord,
  GoogleOAuthConfigStatus,
  GoogleOAuthToolCatalogEntry,
  GoogleOAuthStatus,
  IndexSelection,
  IngestionJob,
  MoveFilesToGroupResponse,
  MindmapPayloadResponse,
  MindmapShareResponse,
  SourceUsageRecord,
  SettingsResponse,
  UploadItem,
  UrlActionResult,
  UploadResponse,
};

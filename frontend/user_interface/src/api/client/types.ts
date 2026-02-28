type ConversationSummary = {
  id: string;
  name: string;
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
  mode: "ask" | "company_agent";
  actions_taken: AgentActionRecord[];
  sources_used: AgentSourceRecord[];
  next_recommended_steps: string[];
  activity_run_id: string | null;
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

type GoogleOAuthStatus = {
  connected: boolean;
  scopes: string[];
  email?: string | null;
  expires_at?: string | null;
  token_type?: string | null;
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
  ChatResponse,
  ChatStreamEvent,
  ConnectorCredentialRecord,
  ConversationDetail,
  ConversationSummary,
  DeleteFileGroupResponse,
  FileActionResult,
  FileGroupListResponse,
  FileGroupRecord,
  FileGroupResponse,
  FileRecord,
  GoogleOAuthStatus,
  IndexSelection,
  IngestionJob,
  MoveFilesToGroupResponse,
  UploadItem,
  UploadResponse,
};

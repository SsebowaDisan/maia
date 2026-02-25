export type ConversationSummary = {
  id: string;
  name: string;
  user: string;
  is_public: boolean;
  date_created: string;
  date_updated: string;
  message_count: number;
};

export type ConversationDetail = ConversationSummary & {
  data_source: {
    messages?: [string, string][];
    retrieval_messages?: string[];
    [key: string]: unknown;
  };
};

export type ChatResponse = {
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

export type AgentActionRecord = {
  tool_id: string;
  action_class: "read" | "draft" | "execute";
  status: "success" | "failed" | "skipped";
  summary: string;
  started_at?: string;
  ended_at?: string;
  metadata?: Record<string, unknown>;
};

export type AgentSourceRecord = {
  source_type: string;
  label: string;
  url?: string | null;
  file_id?: string | null;
  score?: number | null;
  metadata?: Record<string, unknown>;
};

export type AgentActivityEvent = {
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

export type ChatStreamEvent =
  | { type: "chat_delta"; delta: string; text: string }
  | { type: "info_delta"; delta: string }
  | { type: "plot"; plot: Record<string, unknown> | null }
  | { type: "activity"; event: AgentActivityEvent }
  | { type: "debug"; message: string }
  | { type: string; [key: string]: unknown };

export type IndexSelection = {
  mode: "all" | "select" | "disabled";
  file_ids: string[];
};

export type FileRecord = {
  id: string;
  name: string;
  size: number;
  note: Record<string, unknown>;
  date_created: string;
};

export type FileActionResult = {
  file_id: string;
  status: string;
  message?: string;
};

export type BulkDeleteFilesResponse = {
  index_id: number;
  deleted_ids: string[];
  failed: FileActionResult[];
};

export type FileGroupRecord = {
  id: string;
  name: string;
  file_ids: string[];
  date_created: string;
};

export type FileGroupListResponse = {
  index_id: number;
  groups: FileGroupRecord[];
};

export type FileGroupResponse = {
  index_id: number;
  group: FileGroupRecord;
};

export type MoveFilesToGroupResponse = {
  index_id: number;
  group: FileGroupRecord;
  moved_ids: string[];
  skipped_ids: string[];
};

export type DeleteFileGroupResponse = {
  index_id: number;
  group_id: string;
  status: string;
};

export type UploadItem = {
  file_name: string;
  status: string;
  message?: string;
  file_id?: string;
};

export type UploadResponse = {
  index_id: number;
  file_ids: string[];
  errors: string[];
  items: UploadItem[];
  debug: string[];
};

export type IngestionJob = {
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

export type ConnectorCredentialRecord = {
  tenant_id: string;
  connector_id: string;
  values: Record<string, string>;
  date_updated: string;
};

export type GoogleOAuthStatus = {
  connected: boolean;
  scopes: string[];
  email?: string | null;
  expires_at?: string | null;
  token_type?: string | null;
};

export type AgentLiveEvent = {
  type: string;
  message: string;
  data?: Record<string, unknown>;
  run_id?: string;
  timestamp?: string;
  user_id?: string;
};

function inferApiBase() {
  const envBase = (import.meta as { env?: Record<string, string> }).env?.VITE_API_BASE_URL;
  if (envBase) {
    return envBase;
  }

  if (typeof window === "undefined") {
    return "";
  }

  const { hostname, port } = window.location;
  // Dev frontend usually runs on Vite (:5173/:4173) while backend is on :8000.
  if (port === "5173" || port === "4173") {
    return `http://${hostname || "127.0.0.1"}:8000`;
  }

  return "";
}

const API_BASE = inferApiBase();

export function getRawFileUrl(fileId: string): string {
  return `${API_BASE}/api/uploads/files/${encodeURIComponent(fileId)}/raw`;
}

export function getAgentEventSnapshotUrl(runId: string, eventId: string): string {
  return `${API_BASE}/api/agent/runs/${encodeURIComponent(runId)}/events/${encodeURIComponent(eventId)}/snapshot`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.headers || {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export function listConversations() {
  return request<ConversationSummary[]>("/api/conversations");
}

export function createConversation() {
  return request<ConversationDetail>("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
}

export function getConversation(conversationId: string) {
  return request<ConversationDetail>(`/api/conversations/${conversationId}`);
}

export function updateConversation(
  conversationId: string,
  payload: {
    name?: string | null;
    is_public?: boolean | null;
  },
) {
  return request<ConversationDetail>(`/api/conversations/${conversationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deleteConversation(conversationId: string) {
  return request<{ status: string }>(`/api/conversations/${conversationId}`, {
    method: "DELETE",
  });
}

export function sendChat(
  message: string,
  conversationId: string | null,
  options?: {
    indexSelection?: Record<string, IndexSelection>;
    citation?: string;
    useMindmap?: boolean;
    agentMode?: "ask" | "company_agent";
    agentGoal?: string;
    accessMode?: "restricted" | "full_access";
  },
) {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      index_selection: options?.indexSelection ?? {},
      citation: options?.citation,
      use_mindmap: options?.useMindmap,
      agent_mode: options?.agentMode ?? "ask",
      agent_goal: options?.agentGoal,
      access_mode: options?.accessMode,
    }),
  });
}

function parseSseBlock(block: string): { event: string; payload: unknown } | null {
  const lines = block
    .split("\n")
    .map((line) => line.trimEnd())
    .filter(Boolean);
  if (!lines.length) {
    return null;
  }
  let eventName = "message";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  const dataText = dataLines.join("\n");
  if (!dataText) {
    return { event: eventName, payload: {} };
  }
  try {
    return { event: eventName, payload: JSON.parse(dataText) };
  } catch {
    return { event: eventName, payload: { raw: dataText } };
  }
}

export async function sendChatStream(
  message: string,
  conversationId: string | null,
  options: {
    indexSelection?: Record<string, IndexSelection>;
    citation?: string;
    useMindmap?: boolean;
    agentMode?: "ask" | "company_agent";
    agentGoal?: string;
    accessMode?: "restricted" | "full_access";
    onEvent?: (event: ChatStreamEvent) => void;
    idleTimeoutMs?: number;
  },
) {
  const controller = new AbortController();
  const idleTimeoutMs = Math.max(5000, options.idleTimeoutMs ?? 45000);
  let timer: number | null = null;
  const armTimeout = () => {
    if (timer) {
      window.clearTimeout(timer);
    }
    timer = window.setTimeout(() => {
      controller.abort();
    }, idleTimeoutMs);
  };
  armTimeout();

  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    signal: controller.signal,
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      index_selection: options?.indexSelection ?? {},
      citation: options?.citation,
      use_mindmap: options?.useMindmap,
      agent_mode: options?.agentMode ?? "ask",
      agent_goal: options?.agentGoal,
      access_mode: options?.accessMode,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Stream request failed: ${response.status}`);
  }
  if (!response.body) {
    throw new Error("No stream body returned by backend.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let donePayload: ChatResponse | null = null;

  while (true) {
    const read = await reader.read();
    if (read.done) {
      break;
    }
    armTimeout();
    buffer += decoder.decode(read.value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const parsed = parseSseBlock(block);
      if (!parsed) {
        continue;
      }
      if (parsed.event === "done") {
        donePayload = parsed.payload as ChatResponse;
        continue;
      }
      if (parsed.event === "error") {
        const detail =
          (parsed.payload as { detail?: string })?.detail || "Unknown streaming error";
        if (timer) {
          window.clearTimeout(timer);
          timer = null;
        }
        throw new Error(detail);
      }
      options.onEvent?.(parsed.payload as ChatStreamEvent);
    }
  }

  if (buffer.trim()) {
    const parsed = parseSseBlock(buffer);
    if (parsed?.event === "done") {
      donePayload = parsed.payload as ChatResponse;
    } else if (parsed?.event === "error") {
      const detail =
        (parsed.payload as { detail?: string })?.detail || "Unknown streaming error";
      throw new Error(detail);
    } else if (parsed) {
      options.onEvent?.(parsed.payload as ChatStreamEvent);
    }
  }

  if (!donePayload) {
    if (timer) {
      window.clearTimeout(timer);
      timer = null;
    }
    throw new Error("Stream ended without final payload.");
  }
  if (timer) {
    window.clearTimeout(timer);
    timer = null;
  }
  return donePayload;
}

export async function uploadFiles(
  files: FileList,
  options?: {
    reindex?: boolean;
    scope?: "persistent" | "chat_temp";
  },
) {
  const formData = new FormData();
  for (const file of Array.from(files)) {
    formData.append("files", file);
  }
  formData.append("reindex", String(options?.reindex ?? true));
  formData.append("scope", options?.scope ?? "persistent");

  return request<UploadResponse>("/api/uploads/files", {
    method: "POST",
    body: formData,
  });
}

export function uploadUrls(
  urlText: string,
  options?: {
    reindex?: boolean;
    web_crawl_depth?: number;
    web_crawl_max_pages?: number;
    web_crawl_same_domain_only?: boolean;
    include_pdfs?: boolean;
    include_images?: boolean;
  },
) {
  const urls = urlText
    .split("\n")
    .map((url) => url.trim())
    .filter(Boolean);

  return request<UploadResponse>("/api/uploads/urls", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      urls,
      reindex: options?.reindex ?? true,
      web_crawl_depth: options?.web_crawl_depth ?? 0,
      web_crawl_max_pages: options?.web_crawl_max_pages ?? 0,
      web_crawl_same_domain_only: options?.web_crawl_same_domain_only ?? true,
      include_pdfs: options?.include_pdfs ?? true,
      include_images: options?.include_images ?? true,
    }),
  });
}

export function listFiles(options?: { includeChatTemp?: boolean }) {
  const query = new URLSearchParams();
  if (options?.includeChatTemp) {
    query.set("include_chat_temp", "true");
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<{ index_id: number; files: FileRecord[] }>(`/api/uploads/files${suffix}`);
}

export function deleteFiles(
  fileIds: string[],
  options?: {
    indexId?: number;
  },
) {
  return request<BulkDeleteFilesResponse>("/api/uploads/files/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_ids: fileIds,
      index_id: options?.indexId,
    }),
  });
}

export function listFileGroups(options?: { indexId?: number }) {
  const query = new URLSearchParams();
  if (typeof options?.indexId === "number") {
    query.set("index_id", String(options.indexId));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<FileGroupListResponse>(`/api/uploads/groups${suffix}`);
}

export function createFileGroup(
  name: string,
  fileIds: string[],
  options?: {
    indexId?: number;
  },
) {
  const payload = {
    name,
    file_ids: fileIds,
    index_id: options?.indexId,
  };
  const movePayload = {
    file_ids: fileIds,
    group_name: name,
    mode: "append",
    index_id: options?.indexId,
  };

  const isLegacyMethodIssue = (error: unknown) => {
    const text = String(error || "");
    return (
      text.includes("Method Not Allowed") ||
      text.includes("Not Found") ||
      text.includes("404") ||
      text.includes("405")
    );
  };

  const createQuery = new URLSearchParams();
  createQuery.set("name", name);
  if (typeof options?.indexId === "number") {
    createQuery.set("index_id", String(options.indexId));
  }
  if (fileIds.length) {
    createQuery.set("file_ids", fileIds.join(","));
  }

  const attempts: Array<() => Promise<MoveFilesToGroupResponse>> = [
    () =>
      request<MoveFilesToGroupResponse>("/api/uploads/groups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    () =>
      request<MoveFilesToGroupResponse>("/api/uploads/groups/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(movePayload),
      }),
    () =>
      request<MoveFilesToGroupResponse>("/api/uploads/groups", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    () =>
      request<MoveFilesToGroupResponse>("/api/uploads/groups/move", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(movePayload),
      }),
    () => request<MoveFilesToGroupResponse>(`/api/uploads/groups/create?${createQuery.toString()}`),
  ];

  return (async () => {
    let lastError: unknown = null;
    for (const attempt of attempts) {
      try {
        return await attempt();
      } catch (error) {
        lastError = error;
        if (!isLegacyMethodIssue(error)) {
          throw error;
        }
      }
    }
    if (isLegacyMethodIssue(lastError)) {
      throw new Error(
        "Group API is not available on the running backend process. Restart the Maia API server and refresh the page.",
      );
    }
    throw lastError || new Error("Unable to create group.");
  })();
}

export function renameFileGroup(
  groupId: string,
  name: string,
  options?: {
    indexId?: number;
  },
) {
  return request<FileGroupResponse>(`/api/uploads/groups/${encodeURIComponent(groupId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      index_id: options?.indexId,
    }),
  });
}

export function deleteFileGroup(
  groupId: string,
  options?: {
    indexId?: number;
  },
) {
  const query = new URLSearchParams();
  if (typeof options?.indexId === "number") {
    query.set("index_id", String(options.indexId));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<DeleteFileGroupResponse>(
    `/api/uploads/groups/${encodeURIComponent(groupId)}${suffix}`,
    {
      method: "DELETE",
    },
  );
}

export function moveFilesToGroup(
  fileIds: string[],
  options?: {
    groupId?: string;
    groupName?: string;
    mode?: "append" | "replace";
    indexId?: number;
  },
) {
  return request<MoveFilesToGroupResponse>("/api/uploads/groups/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_ids: fileIds,
      group_id: options?.groupId,
      group_name: options?.groupName,
      mode: options?.mode ?? "append",
      index_id: options?.indexId,
    }),
  });
}

export async function createFileIngestionJob(
  files: FileList,
  options?: {
    reindex?: boolean;
    indexId?: number;
  },
) {
  const formData = new FormData();
  for (const file of Array.from(files)) {
    formData.append("files", file);
  }
  formData.append("reindex", String(options?.reindex ?? true));
  if (typeof options?.indexId === "number") {
    formData.append("index_id", String(options.indexId));
  }

  return request<IngestionJob>("/api/uploads/files/jobs", {
    method: "POST",
    body: formData,
  });
}

export function createUrlIngestionJob(
  urlText: string,
  options?: {
    reindex?: boolean;
    indexId?: number;
    web_crawl_depth?: number;
    web_crawl_max_pages?: number;
    web_crawl_same_domain_only?: boolean;
    include_pdfs?: boolean;
    include_images?: boolean;
  },
) {
  const urls = urlText
    .split("\n")
    .map((url) => url.trim())
    .filter(Boolean);

  return request<IngestionJob>("/api/uploads/urls/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      urls,
      index_id: options?.indexId,
      reindex: options?.reindex ?? true,
      web_crawl_depth: options?.web_crawl_depth ?? 0,
      web_crawl_max_pages: options?.web_crawl_max_pages ?? 0,
      web_crawl_same_domain_only: options?.web_crawl_same_domain_only ?? true,
      include_pdfs: options?.include_pdfs ?? true,
      include_images: options?.include_images ?? true,
    }),
  });
}

export function listIngestionJobs(limit = 50) {
  return request<IngestionJob[]>(`/api/uploads/jobs?limit=${encodeURIComponent(String(limit))}`);
}

export function getIngestionJob(jobId: string) {
  return request<IngestionJob>(`/api/uploads/jobs/${encodeURIComponent(jobId)}`);
}

export function buildRawFileUrl(fileId: string, options?: { indexId?: number; download?: boolean }) {
  const query = new URLSearchParams();
  if (typeof options?.indexId === "number") {
    query.set("index_id", String(options.indexId));
  }
  if (options?.download) {
    query.set("download", "true");
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return `${API_BASE}/api/uploads/files/${encodeURIComponent(fileId)}/raw${suffix}`;
}

export function getAgentRunEvents(runId: string) {
  return request<Array<{ type: string; payload: unknown }>>(
    `/api/agent/runs/${encodeURIComponent(runId)}/events`,
  );
}

export function exportAgentRunEvents(runId: string) {
  return request<{
    run_id: string;
    run_started: Record<string, unknown>;
    run_completed: Record<string, unknown>;
    total_rows: number;
    total_events: number;
    events: Array<Record<string, unknown>>;
  }>(`/api/agent/runs/${encodeURIComponent(runId)}/events/export`);
}

export function listAgentTools() {
  return request<Array<Record<string, unknown>>>("/api/agent/tools");
}

export function listConnectorHealth() {
  return request<Array<Record<string, unknown>>>("/api/agent/connectors/health");
}

export function listConnectorCredentials() {
  return request<ConnectorCredentialRecord[]>("/api/agent/connectors/credentials");
}

export function upsertConnectorCredentials(
  connectorId: string,
  values: Record<string, string>,
) {
  return request<ConnectorCredentialRecord>("/api/agent/connectors/credentials", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      connector_id: connectorId,
      values,
    }),
  });
}

export function deleteConnectorCredentials(connectorId: string) {
  return request<{ status: string; connector_id: string }>(
    `/api/agent/connectors/credentials/${encodeURIComponent(connectorId)}`,
    {
      method: "DELETE",
    },
  );
}

export function startGoogleOAuth(options?: {
  redirectUri?: string;
  scopes?: string[];
  state?: string;
}) {
  const query = new URLSearchParams();
  if (options?.redirectUri) {
    query.set("redirect_uri", options.redirectUri);
  }
  if (options?.scopes && options.scopes.length > 0) {
    query.set("scopes", options.scopes.join(","));
  }
  if (options?.state) {
    query.set("state", options.state);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<{
    authorize_url: string;
    state: string;
    redirect_uri: string;
    scopes: string[];
  }>(`/api/agent/oauth/google/start${suffix}`);
}

export function exchangeGoogleOAuthCode(payload: {
  code: string;
  redirectUri?: string;
  state?: string;
  connectorIds?: string[];
}) {
  return request<{
    status: string;
    stored_connectors: string[];
    token_type: string;
    expires_at: string | null;
    refresh_token_stored: boolean;
    deprecated?: boolean;
    warning?: string;
  }>("/api/agent/oauth/google/exchange", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code: payload.code,
      redirect_uri: payload.redirectUri,
      state: payload.state,
      connector_ids: payload.connectorIds,
    }),
  });
}

export function getGoogleOAuthStatus() {
  return request<GoogleOAuthStatus>("/api/agent/oauth/google/status");
}

export function disconnectGoogleOAuth() {
  return request<{
    status: string;
    revoked: boolean;
    cleared_connectors: string[];
  }>("/api/agent/oauth/google/disconnect", {
    method: "POST",
  });
}

export function subscribeAgentEvents(options?: {
  runId?: string;
  replay?: number;
  onReady?: (payload: Record<string, unknown>) => void;
  onEvent?: (event: AgentLiveEvent) => void;
  onError?: () => void;
}) {
  const query = new URLSearchParams();
  if (options?.runId) {
    query.set("run_id", options.runId);
  }
  if (typeof options?.replay === "number") {
    query.set("replay", String(options.replay));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const eventSource = new EventSource(`${API_BASE}/api/agent/events${suffix}`);

  eventSource.addEventListener("ready", (event) => {
    try {
      const parsed = JSON.parse((event as MessageEvent<string>).data || "{}");
      options?.onReady?.(parsed);
    } catch {
      options?.onReady?.({});
    }
  });
  eventSource.addEventListener("event", (event) => {
    try {
      const parsed = JSON.parse((event as MessageEvent<string>).data || "{}");
      options?.onEvent?.(parsed as AgentLiveEvent);
    } catch {
      // Ignore malformed event chunks.
    }
  });
  eventSource.onerror = () => {
    options?.onError?.();
  };

  return () => {
    eventSource.close();
  };
}

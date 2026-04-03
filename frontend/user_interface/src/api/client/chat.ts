import { request } from "./core";
import type {
  ChatResponse,
  ChatStreamEvent,
  ConversationDetail,
  ConversationSummary,
  IndexSelection,
  MindmapPayloadResponse,
  MindmapShareResponse,
} from "./types";

function listConversations() {
  return request<ConversationSummary[]>("/api/conversations");
}

function createConversation() {
  return request<ConversationDetail>("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
}

function getConversation(conversationId: string) {
  return request<ConversationDetail>(`/api/conversations/${encodeURIComponent(conversationId)}`);
}

function updateConversation(
  conversationId: string,
  payload: {
    name?: string | null;
    is_public?: boolean | null;
  },
) {
  return request<ConversationDetail>(`/api/conversations/${encodeURIComponent(conversationId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function deleteConversation(conversationId: string) {
  return request<{ status: string }>(`/api/conversations/${encodeURIComponent(conversationId)}`, {
    method: "DELETE",
  });
}

function createMindmapShare(
  conversationId: string,
  payload: {
    map: Record<string, unknown>;
    title?: string;
  },
) {
  return request<MindmapShareResponse>(
    `/api/conversations/${encodeURIComponent(conversationId)}/mindmaps/share`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        map: payload.map,
        title: payload.title || undefined,
      }),
    },
  );
}

function getSharedMindmap(shareId: string) {
  return request<MindmapShareResponse>(
    `/api/conversations/mindmaps/shared/${encodeURIComponent(shareId)}`,
  );
}

function getMindmapBySource(options: {
  sourceId: string;
  mapType?: "structure" | "evidence" | "work_graph";
  maxDepth?: number;
  includeReasoningMap?: boolean;
}) {
  const query = new URLSearchParams({
    sourceId: options.sourceId,
    mapType: options.mapType || "structure",
    maxDepth: String(options.maxDepth ?? 4),
    includeReasoningMap: String(options.includeReasoningMap ?? true),
  });
  return request<MindmapPayloadResponse>(`/api/mindmap?${query.toString()}`);
}

function exportMindmapMarkdown(options: {
  sourceId: string;
  mapType?: "structure" | "evidence" | "work_graph";
  maxDepth?: number;
  includeReasoningMap?: boolean;
}) {
  const query = new URLSearchParams({
    sourceId: options.sourceId,
    mapType: options.mapType || "structure",
    maxDepth: String(options.maxDepth ?? 4),
    includeReasoningMap: String(options.includeReasoningMap ?? true),
  });
  return fetchApi(`/api/mindmap/export/markdown?${query.toString()}`).then((response) => {
    if (!response.ok) {
      return response.text().then((text) => {
        throw new Error(text || `Request failed: ${response.status}`);
      });
    }
    return response.text();
  });
}

function sendChat(
  message: string,
  conversationId: string | null,
  options?: {
    indexSelection?: Record<string, IndexSelection>;
    citation?: string;
    language?: string;
    useMindmap?: boolean;
    mindmapSettings?: Record<string, unknown>;
    mindmapFocus?: Record<string, unknown>;
    settingOverrides?: Record<string, unknown>;
    agentMode?: "ask" | "company_agent" | "deep_search";
    agentId?: string;
    agentGoal?: string;
    accessMode?: "restricted" | "full_access";
    attachments?: Array<{ name: string; fileId?: string }>;
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
      language: options?.language,
      use_mindmap: options?.useMindmap,
      mindmap_settings: options?.mindmapSettings ?? {},
      mindmap_focus: options?.mindmapFocus ?? {},
      setting_overrides: options?.settingOverrides ?? {},
      agent_mode: options?.agentMode ?? "ask",
      agent_id: options?.agentId ?? null,
      agent_goal: options?.agentGoal,
      access_mode: options?.accessMode,
      attachments: (options?.attachments || []).map((item) => ({
        name: item.name,
        file_id: item.fileId,
      })),
    }),
  });
}

async function sendChatStream(
  message: string,
  conversationId: string | null,
  options: {
    indexSelection?: Record<string, IndexSelection>;
    citation?: string;
    language?: string;
    useMindmap?: boolean;
    mindmapSettings?: Record<string, unknown>;
    mindmapFocus?: Record<string, unknown>;
    settingOverrides?: Record<string, unknown>;
    agentMode?: "ask" | "company_agent" | "deep_search";
    agentId?: string;
    agentGoal?: string;
    accessMode?: "restricted" | "full_access";
    attachments?: Array<{ name: string; fileId?: string }>;
    onEvent?: (event: ChatStreamEvent) => void;
    idleTimeoutMs?: number;
  },
) {
  const response = await sendChat(message, conversationId, {
    indexSelection: options?.indexSelection,
    citation: options?.citation,
    language: options?.language,
    useMindmap: options?.useMindmap,
    mindmapSettings: options?.mindmapSettings,
    mindmapFocus: options?.mindmapFocus,
    settingOverrides: options?.settingOverrides,
    agentMode: options?.agentMode,
    agentId: options?.agentId,
    agentGoal: options?.agentGoal,
    accessMode: options?.accessMode,
    attachments: options?.attachments,
  });
  options.onEvent?.({
    type: "chat_response",
    response,
  });
  return response;
}

export {
  createMindmapShare,
  createConversation,
  deleteConversation,
  exportMindmapMarkdown,
  getMindmapBySource,
  getSharedMindmap,
  getConversation,
  listConversations,
  sendChat,
  sendChatStream,
  updateConversation,
};

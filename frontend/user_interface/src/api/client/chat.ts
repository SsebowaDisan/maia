import { fetchApi, request } from "./core";
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
    useMindmap?: boolean;
    mindmapSettings?: Record<string, unknown>;
    mindmapFocus?: Record<string, unknown>;
    settingOverrides?: Record<string, unknown>;
    agentMode?: "ask" | "company_agent" | "deep_search";
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
      use_mindmap: options?.useMindmap,
      mindmap_settings: options?.mindmapSettings ?? {},
      mindmap_focus: options?.mindmapFocus ?? {},
      setting_overrides: options?.settingOverrides ?? {},
      agent_mode: options?.agentMode ?? "ask",
      agent_goal: options?.agentGoal,
      access_mode: options?.accessMode,
      attachments: (options?.attachments || []).map((item) => ({
        name: item.name,
        file_id: item.fileId,
      })),
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

async function sendChatStream(
  message: string,
  conversationId: string | null,
  options: {
    indexSelection?: Record<string, IndexSelection>;
    citation?: string;
    useMindmap?: boolean;
    mindmapSettings?: Record<string, unknown>;
    mindmapFocus?: Record<string, unknown>;
    settingOverrides?: Record<string, unknown>;
    agentMode?: "ask" | "company_agent" | "deep_search";
    agentGoal?: string;
    accessMode?: "restricted" | "full_access";
    attachments?: Array<{ name: string; fileId?: string }>;
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

  const response = await fetchApi("/api/chat/stream", {
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
      mindmap_settings: options?.mindmapSettings ?? {},
      mindmap_focus: options?.mindmapFocus ?? {},
      setting_overrides: options?.settingOverrides ?? {},
      agent_mode: options?.agentMode ?? "ask",
      agent_goal: options?.agentGoal,
      access_mode: options?.accessMode,
      attachments: (options?.attachments || []).map((item) => ({
        name: item.name,
        file_id: item.fileId,
      })),
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

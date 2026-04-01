import type { CitationFocus, ChatAttachment, ChatTurn, ClarificationPrompt, AgentActivityEvent } from "../../../types";
import type { AccessMode, AgentMode, SendMessageOptions } from "../constants";

const MODE_SCOPE_STATEMENTS: Record<string, string> = {
  rag: "Library mode: I will search, summarize, and answer from Axon Group files and URLs, grounding each claim in those sources.",
  company_agent: "Agent mode: I will execute tools and complete the workflow end-to-end.",
  deep_search:
    "Deep search: I will query multiple sources, synthesize evidence, and cite each key claim.",
  web_search:
    "Web search: I will browse relevant sources on the web and summarize findings with citations.",
};

function normalizeModeValue(value: unknown, fallback: string): string {
  const normalized = String(value || "").trim().toLowerCase();
  return normalized || fallback;
}

function resolveReturnedTurnMode({
  effectiveMode,
  responseMode,
  responseModeRequested,
  responseModeActual,
  infoPanel,
  webOnlyResearchRequested,
}: {
  effectiveMode: AgentMode;
  responseMode?: string | null;
  responseModeRequested?: string | null;
  responseModeActual?: string | null;
  infoPanel?: Record<string, unknown> | null;
  webOnlyResearchRequested: boolean;
}): ChatTurn["mode"] {
  const modeVariant = normalizeModeValue(
    (infoPanel as { mode_variant?: unknown } | null)?.mode_variant,
    "",
  );
  if (
    effectiveMode === "rag" ||
    modeVariant === "rag" ||
    normalizeModeValue(responseModeRequested, "") === "rag" ||
    normalizeModeValue(responseModeActual, "") === "rag"
  ) {
    return "rag";
  }
  const normalizedResponseMode = normalizeModeValue(responseMode, effectiveMode);
  if (normalizedResponseMode === "deep_search" && webOnlyResearchRequested) {
    return "web_search";
  }
  return normalizedResponseMode as ChatTurn["mode"];
}

function deriveModeStatus({
  isFirstTurn,
  requestedMode,
  actualMode,
  existingStatus,
  message,
}: {
  isFirstTurn: boolean;
  requestedMode: string;
  actualMode: string;
  existingStatus: ChatTurn["modeStatus"];
  message: string | null;
}): ChatTurn["modeStatus"] {
  if (requestedMode && actualMode && requestedMode !== actualMode) {
    return {
      state: "downgraded",
      requestedMode,
      actualMode,
      message: message || `Mode changed from ${requestedMode} to ${actualMode}.`,
      scopeStatement: existingStatus?.scopeStatement || null,
    };
  }
  if (existingStatus) {
    return existingStatus;
  }
  if (isFirstTurn && requestedMode !== "ask") {
    return {
      state: "committed",
      requestedMode,
      actualMode,
      scopeStatement: MODE_SCOPE_STATEMENTS[requestedMode] || null,
      message: message || null,
    };
  }
  return null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function isAgentActivityPayload(payload: unknown): payload is AgentActivityEvent {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const candidate = payload as Record<string, unknown>;
  return (
    typeof candidate.event_id === "string" &&
    candidate.event_id.trim().length > 0 &&
    typeof candidate.event_type === "string" &&
    candidate.event_type.trim().length > 0 &&
    typeof candidate.run_id === "string" &&
    candidate.run_id.trim().length > 0
  );
}

type SendConversationMessageParams = {
  message: string;
  attachments?: ChatAttachment[];
  options?: SendMessageOptions;
  composerMode: AgentMode;
  accessMode: AccessMode;
  chatTurnsLength: number;
  defaultIndexId: number | null;
  citationMode: string;
  mindmapEnabled: boolean;
  mindmapMaxDepth: number;
  mindmapIncludeReasoning: boolean;
  mindmapMapType: string;
  selectedConversationId: string | null;
  selectedProjectId: string;
  refreshConversations: () => Promise<void>;
  setCitationFocus: (value: CitationFocus | null) => void;
  setIsSending: (value: boolean) => void;
  setIsActivityStreaming: (value: boolean) => void;
  setClarificationPrompt: (
    value:
      | ClarificationPrompt
      | null
      | ((previous: ClarificationPrompt | null) => ClarificationPrompt | null),
  ) => void;
  setInfoText: (value: string | ((previous: string) => string)) => void;
  setActivityEvents: (value: AgentActivityEvent[]) => void;
  setSelectedTurnIndex: (value: number | null) => void;
  setChatTurns: (updater: (prev: ChatTurn[]) => ChatTurn[]) => void;
  setConversationProjects: (updater: (prev: Record<string, string>) => Record<string, string>) => void;
  setConversationModes: (updater: (prev: Record<string, AgentMode>) => Record<string, AgentMode>) => void;
  setComposerMode: (value: AgentMode) => void;
  setSelectedConversationId: (value: string) => void;
  setConversationMindmapSettings: (
    updater: (
      prev: Record<
        string,
        {
          enabled: boolean;
          maxDepth: number;
          includeReasoningMap: boolean;
          mapType: "structure" | "evidence" | "work_graph" | "context_mindmap";
        }
      >,
    ) => Record<
      string,
      {
        enabled: boolean;
        maxDepth: number;
        includeReasoningMap: boolean;
        mapType: "structure" | "evidence" | "work_graph" | "context_mindmap";
      }
    >,
  ) => void;
};

export {
  MODE_SCOPE_STATEMENTS,
  asRecord,
  deriveModeStatus,
  isAgentActivityPayload,
  normalizeModeValue,
  resolveReturnedTurnMode,
};
export type { SendConversationMessageParams };

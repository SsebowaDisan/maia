import {
  assembleAndRunWorkflowWithStream,
  createConversation,
  sendChat,
  sendChatStream,
  type ChatResponse,
  type WorkflowRunEvent,
} from "../../../api/client";
import { fallbackAssistantBlocks, normalizeCanvasDocuments, normalizeMessageBlocks } from "../../messageBlocks";
import { useCanvasStore } from "../../stores/canvasStore";
import { DEFAULT_PROJECT_ID } from "../constants";
import type {
  AgentActivityEvent,
  ChatTurn,
  CitationFocus,
  ChatAttachment,
  ClarificationPrompt,
} from "../../types";
import { clarificationPromptFromEvent } from "./clarification";
import { extractCanvasDocumentFromToolEvent } from "../eventHelpers";
import {
  DEEP_SEARCH_SETTING_OVERRIDES,
  RAG_SETTING_OVERRIDES,
  type AccessMode,
  type AgentMode,
  normalizeMindmapMapType,
  type SendMessageOptions,
} from "./constants";

const MODE_SCOPE_STATEMENTS: Record<string, string> = {
  rag: "RAG mode: I will answer from files and indexed URLs already in Maia, grounding each claim in those sources.",
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

function deriveWorkflowEventData(row: Record<string, unknown>, data: Record<string, unknown>): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...data };
  const fallbackKeys = [
    "url",
    "source_url",
    "target_url",
    "page_url",
    "final_url",
    "link",
    "tool_id",
    "scene_surface",
    "scene_family",
    "brand_slug",
    "connector_id",
    "connector_label",
    "from_agent",
    "to_agent",
    "from_role",
    "to_role",
    "next_role",
    "agent_id",
    "agent_role",
    "owner_role",
    "step_id",
    "message",
    "question",
    "answer",
    "summary",
    "progress",
    "run_id",
  ] as const;
  for (const key of fallbackKeys) {
    if (merged[key] !== undefined) {
      continue;
    }
    if (row[key] !== undefined) {
      merged[key] = row[key];
    }
  }
  return merged;
}

function workflowEventTitle(eventType: string): string {
  const normalized = String(eventType || "")
    .trim()
    .replace(/[._-]+/g, " ")
    .toLowerCase();
  if (!normalized) {
    return "Activity";
  }
  return normalized.replace(/\b\w/g, (char) => char.toUpperCase());
}

function toActivityEventFromWorkflowEvent(
  event: WorkflowRunEvent,
  options: {
    fallbackRunId: string;
    index: number;
  },
): AgentActivityEvent | null {
  const { fallbackRunId, index } = options;
  const row = asRecord(event);
  const data = asRecord(row.data);
  const metadata = asRecord(row.metadata);
  const resolvedData = deriveWorkflowEventData(row, data);
  const explicitEventType = normalizeModeValue(row.event_type, "").toLowerCase();
  const fallbackEventType = normalizeModeValue(
    row.type || data.type || metadata.type || metadata.event_type,
    "",
  ).toLowerCase();
  const eventType =
    explicitEventType && explicitEventType !== "event"
      ? explicitEventType
      : fallbackEventType || explicitEventType;
  if (!eventType || eventType === "done") {
    return null;
  }
  const runId = String(row.run_id || resolvedData.run_id || data.run_id || fallbackRunId).trim();
  if (!runId) {
    return null;
  }
  const title = String(row.title || "").trim() || workflowEventTitle(eventType);
  const detail = String(
    row.detail ||
      row.error ||
      row.message ||
      row.text ||
      row.delta ||
      data.detail ||
      data.error ||
      data.message ||
      data.text ||
      data.delta ||
      "",
  ).trim();
  const eventId = String(row.event_id || "").trim() || `${runId}-${eventType}-${index}`;
  const eventFamily =
    eventType.startsWith("assembly_") ||
    eventType.startsWith("brain_") ||
    eventType.startsWith("agent_dialogue")
      ? "plan"
      : eventType.startsWith("workflow_") || eventType.startsWith("execution_")
      ? "workflow"
      : undefined;
  return {
    event_id: eventId,
    run_id: runId,
    event_type: eventType,
    title,
    detail,
    timestamp: new Date().toISOString(),
    stage: eventFamily === "plan" ? "plan" : "execute",
    status: eventType.includes("error") || eventType.includes("failed") ? "failed" : "info",
    data: resolvedData,
    metadata,
    event_family: eventFamily,
    event_render_mode: eventFamily === "plan" ? "animate_live" : undefined,
  };
}

function summarizeBrainRun(events: AgentActivityEvent[]): string {
  const latestError = [...events]
    .reverse()
    .find((event) =>
      ["assembly_error", "execution_error", "workflow_failed", "error"].includes(
        String(event.event_type || "").trim().toLowerCase(),
      ),
    );
  if (latestError) {
    return latestError.detail
      ? `Brain run failed: ${latestError.detail}`
      : `Brain run failed at ${latestError.title}.`;
  }

  const executionComplete = [...events].reverse().find((event) => {
    const type = String(event.event_type || "").trim().toLowerCase();
    return type === "execution_complete" || type === "workflow_completed";
  });
  const outputRecord = asRecord(executionComplete?.data?.outputs);
  const deliverySentEvent = [...events]
    .reverse()
    .find((event) => String(event.event_type || "").trim().toLowerCase() === "email_sent");
  const rankedOutputs = Object.entries(outputRecord)
    .map(([key, value]) => {
      const preview = String(value || "").replace(/\r\n/g, "\n").trim();
      const lowered = preview.toLowerCase();
      let score = 0;
      if (preview.includes("## Evidence Citations")) {
        score += 5;
      }
      if (/\[\d+\]/.test(preview)) {
        score += 3;
      }
      if (/##\s+(executive summary|key findings|summary|findings)/i.test(preview)) {
        score += 2;
      }
      if (/email sent to|sent cited email to/i.test(preview)) {
        score -= 5;
      }
      if (/^to:\s.+\nsubject:\s/im.test(preview)) {
        score -= 2;
      }
      if (/draft|summary|research|report|findings/i.test(key)) {
        score += 2;
      }
      score += Math.min(4, Math.floor(preview.length / 700));
      return { key, preview, score };
    })
    .filter((row) => row.preview)
    .sort((left, right) => right.score - left.score);
  const citedResearchBrief = rankedOutputs.find(
    (row) =>
      /\[\d+\]/.test(row.preview) &&
      !/^subject:\s/im.test(row.preview) &&
      !/^to:\s/im.test(row.preview) &&
      /##\s+(executive summary|key findings|summary|findings)/i.test(row.preview),
  );
  if (citedResearchBrief) {
    const recipient = String(deliverySentEvent?.data?.recipient || "").trim();
    const confirmation = recipient ? `\n\nEmail sent to ${recipient}.` : "";
    return `${citedResearchBrief.preview}${confirmation}`;
  }
  const primaryRichOutput = rankedOutputs[0]?.preview || "";
  if (primaryRichOutput && (primaryRichOutput.includes("## Evidence Citations") || /\[\d+\]/.test(primaryRichOutput))) {
    return primaryRichOutput;
  }
  const outputLines = Object.entries(outputRecord)
    .slice(0, 4)
    .map(([key, value]) => {
      const preview = String(value || "").replace(/\s+/g, " ").trim();
      if (!preview) {
        return null;
      }
      return `- ${key}: ${preview.slice(0, 220)}${preview.length > 220 ? "..." : ""}`;
    })
    .filter((line): line is string => Boolean(line));

  const workflowSaved = [...events]
    .reverse()
    .find((event) => String(event.event_type || "").trim().toLowerCase() === "workflow_saved");
  const workflowId = String(workflowSaved?.data?.workflow_id || "").trim();

  if (outputLines.length) {
    return [
      "Brain assembled and executed the workflow successfully.",
      "",
      "Results:",
      ...outputLines,
      workflowId ? "" : "",
      workflowId ? `Workflow ID: ${workflowId}` : "",
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (workflowId) {
    return `Brain assembled and executed the workflow successfully (workflow ${workflowId}).`;
  }
  return "Brain assembled and executed the workflow successfully.";
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
      prev: Record<string, {
        enabled: boolean;
        maxDepth: number;
        includeReasoningMap: boolean;
        mapType: "structure" | "evidence" | "work_graph" | "context_mindmap";
      }>,
    ) => Record<string, {
      enabled: boolean;
      maxDepth: number;
      includeReasoningMap: boolean;
      mapType: "structure" | "evidence" | "work_graph" | "context_mindmap";
    }>,
  ) => void;
};

async function sendConversationMessage({
  message,
  attachments,
  options,
  composerMode,
  accessMode,
  chatTurnsLength,
  defaultIndexId,
  citationMode,
  mindmapEnabled,
  mindmapMaxDepth,
  mindmapIncludeReasoning,
  mindmapMapType,
  selectedConversationId,
  selectedProjectId,
  refreshConversations,
  setCitationFocus,
  setIsSending,
  setIsActivityStreaming,
  setClarificationPrompt,
  setInfoText,
  setActivityEvents,
  setSelectedTurnIndex,
  setChatTurns,
  setConversationProjects,
  setConversationModes,
  setComposerMode,
  setSelectedConversationId,
  setConversationMindmapSettings,
}: SendConversationMessageParams) {
  if (!message.trim()) {
    return;
  }

  const effectiveMode = options?.agentMode ?? composerMode;
  const backendMode: AgentMode =
    effectiveMode === "brain" ? "company_agent" : effectiveMode === "rag" ? "ask" : effectiveMode;
  const effectiveAccessMode = options?.accessMode ?? accessMode;
  const orchestratorMode = backendMode === "company_agent" || backendMode === "deep_search";
  const liveStreamMode = orchestratorMode || effectiveMode === "rag";
  const webOnlyResearchRequested =
    backendMode === "deep_search" && Boolean(options?.settingOverrides?.["__research_web_only"]);
  const requestedTurnMode: ChatTurn["mode"] =
    effectiveMode === "deep_search" && webOnlyResearchRequested ? "web_search" : effectiveMode;
  const isFirstTurn = chatTurnsLength === 0;
  const initialRequestedMode = normalizeModeValue(requestedTurnMode || effectiveMode, "ask");
  const initialModeStatus: ChatTurn["modeStatus"] =
    isFirstTurn && initialRequestedMode !== "ask"
      ? {
          state: "committed",
          requestedMode: initialRequestedMode,
          actualMode: initialRequestedMode,
          scopeStatement: MODE_SCOPE_STATEMENTS[initialRequestedMode] || null,
          message: null,
        }
      : null;
  const delayedPendingAssistantMessage = liveStreamMode
    ? effectiveMode === "brain"
      ? "Brain is assembling your team and running the workflow..."
      : backendMode === "deep_search"
        ? webOnlyResearchRequested
          ? "Running web search..."
          : "Running deep search..."
        : effectiveMode === "rag"
          ? "Reviewing the selected files and indexed URLs..."
        : "Starting my desktop..."
    : effectiveMode === "rag"
      ? "Grounding the answer in files and indexed URLs already in Maia..."
      : "Thinking....";
  const firstAttachedFile = (attachments || []).find((item) => Boolean(item.fileId));
  if (firstAttachedFile?.fileId) {
    setCitationFocus({
      fileId: firstAttachedFile.fileId,
      sourceName: String(firstAttachedFile.name || "Uploaded file"),
      extract: "",
      evidenceId: `send-file-preview-${Date.now()}`,
    });
  }

  const attachedFileIds = (attachments || [])
    .map((item) => item.fileId)
    .filter((item): item is string => Boolean(item));

  const pendingTurnIndex = chatTurnsLength;
  const mergedSettingOverrides: Record<string, unknown> = {
    ...(backendMode === "deep_search" ? DEEP_SEARCH_SETTING_OVERRIDES : {}),
    ...(effectiveMode === "rag" ? RAG_SETTING_OVERRIDES : {}),
    ...(options?.settingOverrides || {}),
    ...(effectiveMode === "brain" ? { __brain_mode_enabled: true } : {}),
  };

  setIsSending(true);
  setIsActivityStreaming(liveStreamMode);
  setClarificationPrompt(null);
  setCitationFocus(null);
  setInfoText("");
  setActivityEvents([]);
  setSelectedTurnIndex(pendingTurnIndex);
  setChatTurns((prev) => [
    ...prev,
    {
      user: message,
      assistant: delayedPendingAssistantMessage,
      blocks: fallbackAssistantBlocks(delayedPendingAssistantMessage),
      documents: [],
      plot: null,
      attachments: attachments && attachments.length > 0 ? attachments : undefined,
      info: "",
      mode: requestedTurnMode,
      modeRequested: initialRequestedMode,
      modeActuallyUsed: initialRequestedMode,
      modeStatus: initialModeStatus,
      haltReason: null,
      haltMessage: null,
      activityEvents: [],
      needsHumanReview: false,
      humanReviewNotes: null,
      infoPanel: {},
    },
  ]);

  let streamedEventsLocal: AgentActivityEvent[] = [];
  try {
    const selectionByIndex: Record<string, { mode: "select"; file_ids: string[] }> = {};
    const appendSelection = (indexId: number | null, fileIds: string[]) => {
      if (indexId === null || !fileIds.length) {
        return;
      }
      const key = String(indexId);
      const existing = new Set(selectionByIndex[key]?.file_ids || []);
      for (const fileId of fileIds) {
        const normalized = String(fileId || "").trim();
        if (normalized) {
          existing.add(normalized);
        }
      }
      if (!existing.size) {
        return;
      }
      selectionByIndex[key] = {
        mode: "select",
        file_ids: Array.from(existing),
      };
    };
    appendSelection(defaultIndexId, attachedFileIds);
    const indexSelection = Object.keys(selectionByIndex).length > 0 ? selectionByIndex : undefined;

    const sharedPayload = {
      indexSelection,
      attachments: (attachments || [])
        .map((item) => ({
          name: String(item.name || "").trim(),
          fileId: String(item.fileId || "").trim() || undefined,
        }))
        .filter((item) => Boolean(item.name || item.fileId)),
      citation: options?.citationMode ?? citationMode,
      useMindmap: options?.useMindmap ?? mindmapEnabled,
      mindmapSettings: options?.mindmapSettings ?? {
        max_depth: mindmapMaxDepth,
        include_reasoning_map: mindmapIncludeReasoning,
        map_type: mindmapMapType,
      },
      mindmapFocus: options?.mindmapFocus ?? {},
      settingOverrides: mergedSettingOverrides,
      agentMode: backendMode,
      agentId: options?.agentId,
      accessMode: effectiveAccessMode,
    };

    let response: ChatResponse;
    if (liveStreamMode) {
      let streamedInfo = "";
      const streamedEvents: AgentActivityEvent[] = [];
      let streamedRunId = "";
      let streamedModeRequested = initialRequestedMode;
      let streamedModeActual = initialRequestedMode;
      let streamedModeStatus: ChatTurn["modeStatus"] = initialModeStatus;
      let streamedHaltReason: string | null = null;
      let streamedHaltMessage: string | null = null;
      try {
        if (effectiveMode === "brain") {
          let brainEventIndex = 0;
          const fallbackRunId = `brain_${Date.now()}`;
          await assembleAndRunWorkflowWithStream(message, {
            onEvent: (workflowEvent) => {
              const normalized = toActivityEventFromWorkflowEvent(workflowEvent, {
                fallbackRunId: streamedRunId || fallbackRunId,
                index: ++brainEventIndex,
              });
              if (!normalized) {
                return;
              }
              const payloadRunId = String(normalized.run_id || "").trim();
              if (payloadRunId) {
                streamedRunId = payloadRunId;
              }
              streamedEvents.push(normalized);
              streamedEventsLocal = [...streamedEvents];
              setActivityEvents([...streamedEvents]);
              const liveAssistant = normalized.detail
                ? `${normalized.title}\n${normalized.detail}`
                : normalized.title;
              setChatTurns((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                next[next.length - 1] = {
                  ...(last || {}),
                  assistant: liveAssistant || String(last?.assistant || ""),
                  blocks: fallbackAssistantBlocks(liveAssistant || String(last?.assistant || "")),
                  activityEvents: [...streamedEvents],
                };
                return next;
              });
            },
          });
          let ensuredConversationId = String(selectedConversationId || "").trim();
          if (!ensuredConversationId) {
            try {
              const created = await createConversation();
              ensuredConversationId = String(created.id || "").trim();
            } catch {
              throw new Error("Unable to create a conversation for Brain mode.");
            }
          }
          if (!ensuredConversationId) {
            throw new Error("Unable to resolve a conversation for Brain mode.");
          }
          const answer = summarizeBrainRun(streamedEvents);
          streamedModeRequested = "brain";
          streamedModeActual = "brain";
          streamedModeStatus = deriveModeStatus({
            isFirstTurn,
            requestedMode: "brain",
            actualMode: "brain",
            existingStatus: streamedModeStatus,
            message: null,
          });
          response = {
            conversation_id: ensuredConversationId,
            conversation_name: "Brain run",
            message,
            answer,
            blocks: fallbackAssistantBlocks(answer),
            documents: [],
            info: "",
            plot: null,
            state: {},
            mode: "company_agent",
            actions_taken: [],
            sources_used: [],
            source_usage: [],
            next_recommended_steps: [],
            needs_human_review: false,
            human_review_notes: null,
            web_summary: {},
            info_panel: {},
            activity_run_id: streamedRunId || fallbackRunId,
            mindmap: {},
            halt_reason: null,
            halt_message: null,
            mode_requested: "brain",
            mode_actually_used: "brain",
          };
        } else {
          response = await sendChatStream(message, selectedConversationId, {
            ...sharedPayload,
            agentGoal: message,
            idleTimeoutMs: effectiveMode === "rag" ? 90000 : 60000,
            onEvent: (event) => {
              if (!event || typeof event !== "object") {
                return;
              }
              if (event.type === "chat_delta") {
                setChatTurns((prev) => {
                  const next = [...prev];
                  const last = next[next.length - 1];
                  next[next.length - 1] = {
                    ...(last || {}),
                    user: message,
                    assistant: String(event.text || ""),
                    blocks: fallbackAssistantBlocks(String(event.text || "")),
                  };
                  return next;
                });
                return;
              }
              if (event.type === "info_delta") {
                streamedInfo += String(event.delta || "");
                setInfoText(streamedInfo);
                return;
              }
              if (event.type === "plot") {
                const plotPayload =
                  event.plot && typeof event.plot === "object"
                    ? (event.plot as Record<string, unknown>)
                    : null;
                setChatTurns((prev) => {
                  const next = [...prev];
                  const last = next[next.length - 1];
                  next[next.length - 1] = {
                    ...(last || {}),
                    plot: plotPayload,
                  };
                  return next;
                });
                return;
              }
              if (event.type === "mode_committed") {
                const committedMode = normalizeModeValue(event.mode, streamedModeRequested || "ask");
                streamedModeRequested = committedMode;
                streamedModeActual = committedMode;
                streamedModeStatus = {
                  state: "committed",
                  requestedMode: committedMode,
                  actualMode: committedMode,
                  scopeStatement:
                    String(event.scope_statement || "").trim() ||
                    MODE_SCOPE_STATEMENTS[committedMode] ||
                    null,
                  message: String(event.message || "").trim() || null,
                };
                setChatTurns((prev) => {
                  const next = [...prev];
                  const last = next[next.length - 1];
                  next[next.length - 1] = {
                    ...(last || {}),
                    modeRequested: streamedModeRequested,
                    modeActuallyUsed: streamedModeActual,
                    modeStatus: streamedModeStatus,
                  };
                  return next;
                });
                return;
              }
              if (event.type === "mode_downgraded") {
                streamedModeRequested = normalizeModeValue(
                  event.requested_mode,
                  streamedModeRequested || initialRequestedMode,
                );
                streamedModeActual = normalizeModeValue(
                  event.actual_mode,
                  streamedModeActual || streamedModeRequested || "ask",
                );
                streamedModeStatus = {
                  state: "downgraded",
                  requestedMode: streamedModeRequested,
                  actualMode: streamedModeActual,
                  scopeStatement: streamedModeStatus?.scopeStatement || null,
                  message:
                    String(event.message || "").trim() ||
                    `Mode changed from ${streamedModeRequested} to ${streamedModeActual}.`,
                };
                setChatTurns((prev) => {
                  const next = [...prev];
                  const last = next[next.length - 1];
                  next[next.length - 1] = {
                    ...(last || {}),
                    modeRequested: streamedModeRequested,
                    modeActuallyUsed: streamedModeActual,
                    modeStatus: streamedModeStatus,
                  };
                  return next;
                });
                return;
              }
              if (event.type === "halt") {
                streamedHaltReason = String(event.reason || "").trim() || null;
                streamedHaltMessage = String(event.message || "").trim() || null;
                setChatTurns((prev) => {
                  const next = [...prev];
                  const last = next[next.length - 1];
                  next[next.length - 1] = {
                    ...(last || {}),
                    haltReason: streamedHaltReason,
                    haltMessage: streamedHaltMessage,
                  };
                  return next;
                });
                return;
              }
              if (event.type === "activity" && event.event) {
                if (!isAgentActivityPayload(event.event)) {
                  return;
                }
                const payload = event.event;
                const createdCanvasDocument = extractCanvasDocumentFromToolEvent(payload);
                if (createdCanvasDocument) {
                  const canvasStore = useCanvasStore.getState();
                  canvasStore.upsertDocuments([createdCanvasDocument]);
                  if (String(createdCanvasDocument.modeVariant || "").trim().toLowerCase() !== "rag") {
                    canvasStore.openDocument(createdCanvasDocument.id);
                  }
                }
                const payloadRunId = String(payload.run_id || "").trim();
                if (payloadRunId) {
                  if (!streamedRunId) {
                    streamedRunId = payloadRunId;
                  } else if (payloadRunId !== streamedRunId) {
                    return;
                  }
                }
                const detectedPrompt = clarificationPromptFromEvent({
                  event: payload,
                  originalRequest: message,
                  agentMode: effectiveMode,
                  accessMode: effectiveAccessMode,
                });
                if (detectedPrompt) {
                  setClarificationPrompt((previous: ClarificationPrompt | null) => {
                    if (previous?.runId && previous.runId === detectedPrompt.runId) {
                      return previous;
                    }
                    return detectedPrompt;
                  });
                }
                streamedEvents.push(payload);
                streamedEventsLocal = [...streamedEvents];
                setActivityEvents([...streamedEvents]);
                setChatTurns((prev) => {
                  const next = [...prev];
                  const last = next[next.length - 1];
                  next[next.length - 1] = {
                    ...(last || {}),
                    assistant:
                      last && String(last.assistant || "").trim() === delayedPendingAssistantMessage
                        ? ""
                        : String(last?.assistant || ""),
                    activityEvents: [...streamedEvents],
                  };
                  return next;
                });
              }
            },
          });
          streamedModeRequested = normalizeModeValue(
            response.mode_requested,
            streamedModeRequested || initialRequestedMode,
          );
          streamedModeActual = normalizeModeValue(
            response.mode_actually_used || response.mode,
            streamedModeActual || streamedModeRequested || "ask",
          );
          streamedHaltReason = String(response.halt_reason || streamedHaltReason || "").trim() || null;
          streamedHaltMessage = String(response.halt_message || streamedHaltMessage || "").trim() || null;
          streamedModeStatus = deriveModeStatus({
            isFirstTurn,
            requestedMode: streamedModeRequested,
            actualMode: streamedModeActual,
            existingStatus: streamedModeStatus,
            message: streamedModeStatus?.message || streamedHaltMessage || null,
          });
        }
      } catch (streamError) {
        if (effectiveMode === "brain") {
          throw streamError;
        }
        response = await sendChat(message, selectedConversationId, {
          ...sharedPayload,
          agentGoal: message,
        });
        streamedEventsLocal = [];
        setActivityEvents([]);
        setInfoText((previous) =>
          previous
            ? `${previous}\n\n[Notice] Live activity stream timed out. Used direct response fallback.`
            : "[Notice] Live activity stream timed out. Used direct response fallback.",
        );
        console.warn("Orchestrator stream fallback triggered:", streamError);
      }
    } else {
      response = await sendChat(message, selectedConversationId, sharedPayload);
    }

    const normalizedResponseDocuments = normalizeCanvasDocuments(response.documents);

    setConversationProjects((prev) =>
      prev[response.conversation_id]
        ? prev
        : {
            ...prev,
            [response.conversation_id]: selectedProjectId || DEFAULT_PROJECT_ID,
          },
    );
    setConversationModes((prev) => ({
      ...prev,
      [response.conversation_id]: effectiveMode,
    }));
    setComposerMode(effectiveMode);
    setSelectedConversationId(response.conversation_id);
    setConversationMindmapSettings((prev) => ({
      ...prev,
      [response.conversation_id]: {
        enabled: Boolean(options?.useMindmap ?? mindmapEnabled),
        maxDepth: Number((options?.mindmapSettings?.["max_depth"] as number) ?? mindmapMaxDepth) || 4,
        includeReasoningMap: Boolean(
          (options?.mindmapSettings?.["include_reasoning_map"] as boolean) ?? mindmapIncludeReasoning,
        ),
        mapType: normalizeMindmapMapType(options?.mindmapSettings?.["map_type"] || mindmapMapType),
      },
    }));
    setInfoText(response.info || "");
    const effectiveReturnedMode = (response.mode as AgentMode | undefined) || backendMode;
    const responseModeRequested =
      effectiveMode === "brain"
        ? "brain"
        : normalizeModeValue(response.mode_requested, initialRequestedMode);
    const responseModeActual =
      effectiveMode === "brain"
        ? "brain"
        : normalizeModeValue(
            response.mode_actually_used || effectiveReturnedMode,
            responseModeRequested,
          );
    const resolvedTurnMode = resolveReturnedTurnMode({
      effectiveMode,
      responseMode: effectiveReturnedMode,
      responseModeRequested,
      responseModeActual,
      infoPanel:
        response.info_panel && typeof response.info_panel === "object"
          ? (response.info_panel as Record<string, unknown>)
          : null,
      webOnlyResearchRequested,
    });
    setChatTurns((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      const backendModeMismatch = orchestratorMode && effectiveReturnedMode === "ask";
      const haltReason = String(response.halt_reason || "").trim() || null;
      const haltMessage = String(response.halt_message || "").trim() || null;
      const modeStatus = deriveModeStatus({
        isFirstTurn,
        requestedMode: responseModeRequested,
        actualMode: responseModeActual,
        existingStatus: null,
        message: haltMessage,
      });
      const finalAssistantText = backendModeMismatch
        ? `${response.answer || ""}\n\n[Notice] Backend is not running orchestrator mode. Restart the API server and try again.`
        : response.answer || "";
      next[next.length - 1] = {
        ...(last || {}),
        user: message,
        assistant: finalAssistantText,
        blocks: normalizeMessageBlocks(response.blocks, finalAssistantText),
        documents: normalizedResponseDocuments,
        info: response.info || "",
        plot: response.plot || null,
        mode: resolvedTurnMode,
        modeRequested: responseModeRequested,
        modeActuallyUsed: responseModeActual,
        modeStatus,
        haltReason,
        haltMessage,
        actionsTaken: response.actions_taken || [],
        sourcesUsed: response.sources_used || [],
        sourceUsage: response.source_usage || [],
        nextRecommendedSteps: response.next_recommended_steps || [],
        needsHumanReview: Boolean(response.needs_human_review),
        humanReviewNotes: response.human_review_notes || null,
        webSummary: response.web_summary || {},
        infoPanel: response.info_panel || {},
        mindmap: response.mindmap || {},
        activityRunId: response.activity_run_id || null,
        activityEvents: streamedEventsLocal,
      };
      return next;
    });
    if (resolvedTurnMode === "rag" && normalizedResponseDocuments.length > 0) {
      const canvasStore = useCanvasStore.getState();
      canvasStore.upsertDocuments(normalizedResponseDocuments);
    }
    setActivityEvents(streamedEventsLocal);
    setSelectedTurnIndex(pendingTurnIndex);
    try {
      await refreshConversations();
    } catch (refreshError) {
      const refreshMessage =
        refreshError instanceof Error
          ? refreshError.message
          : String(refreshError || "Unable to refresh conversation list.");
      console.warn("Conversation refresh failed after successful response:", refreshMessage);
      setInfoText((previous) =>
        previous ? `${previous}\n\n[Notice] ${refreshMessage}` : `[Notice] ${refreshMessage}`,
      );
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error || "Unknown request failure");
    setChatTurns((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      next[next.length - 1] = {
        ...(last || {}),
        user: message,
        assistant: `Error: ${errorMessage}`,
        blocks: fallbackAssistantBlocks(`Error: ${errorMessage}`),
        documents: [],
        info: "",
        plot: null,
        mode: requestedTurnMode,
        modeRequested: initialRequestedMode,
        modeActuallyUsed: initialRequestedMode,
        modeStatus: initialModeStatus,
        haltReason: null,
        haltMessage: null,
        needsHumanReview: false,
        humanReviewNotes: null,
        infoPanel: {},
      };
      return next;
    });
  } finally {
    setIsSending(false);
    setIsActivityStreaming(false);
  }
}

export { sendConversationMessage };

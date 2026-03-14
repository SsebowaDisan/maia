import { sendChat, sendChatStream } from "../../../api/client";
import { fallbackAssistantBlocks, normalizeCanvasDocuments, normalizeMessageBlocks } from "../../messageBlocks";
import { DEFAULT_PROJECT_ID } from "../constants";
import type {
  AgentActivityEvent,
  ChatTurn,
  CitationFocus,
  ChatAttachment,
  ClarificationPrompt,
} from "../../types";
import { clarificationPromptFromEvent } from "./clarification";
import {
  DEEP_SEARCH_SETTING_OVERRIDES,
  type AccessMode,
  type AgentMode,
  normalizeMindmapMapType,
  type SendMessageOptions,
} from "./constants";

const MODE_SCOPE_STATEMENTS: Record<string, string> = {
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
  setCitationFocus: (value: CitationFocus) => void;
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
  const effectiveAccessMode = options?.accessMode ?? accessMode;
  const orchestratorMode = effectiveMode === "company_agent" || effectiveMode === "deep_search";
  const webOnlyResearchRequested =
    effectiveMode === "deep_search" && Boolean(options?.settingOverrides?.["__research_web_only"]);
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
  const delayedPendingAssistantMessage = orchestratorMode
    ? effectiveMode === "deep_search"
      ? webOnlyResearchRequested
        ? "Running web search..."
        : "Running deep search..."
      : "Starting my desktop..."
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
  const mergedSettingOverrides: Record<string, unknown> =
    effectiveMode === "deep_search"
      ? {
          ...DEEP_SEARCH_SETTING_OVERRIDES,
          ...(options?.settingOverrides || {}),
        }
      : (options?.settingOverrides || {});

  setIsSending(true);
  setIsActivityStreaming(orchestratorMode);
  setClarificationPrompt(null);
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
      agentMode: effectiveMode,
      accessMode: effectiveAccessMode,
    };

    let response;
    if (orchestratorMode) {
      let streamedInfo = "";
      const streamedEvents: AgentActivityEvent[] = [];
      let streamedRunId = "";
      let streamedModeRequested = initialRequestedMode;
      let streamedModeActual = initialRequestedMode;
      let streamedModeStatus: ChatTurn["modeStatus"] = initialModeStatus;
      let streamedHaltReason: string | null = null;
      let streamedHaltMessage: string | null = null;
      try {
        response = await sendChatStream(message, selectedConversationId, {
          ...sharedPayload,
          agentGoal: message,
          idleTimeoutMs: 60000,
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
      } catch (streamError) {
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
    setChatTurns((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      const effectiveReturnedMode = (response.mode as AgentMode | undefined) || effectiveMode;
      const resolvedTurnMode: ChatTurn["mode"] =
        effectiveReturnedMode === "deep_search" && webOnlyResearchRequested
          ? "web_search"
          : effectiveReturnedMode;
      const backendModeMismatch = orchestratorMode && effectiveReturnedMode === "ask";
      const responseModeRequested = normalizeModeValue(
        response.mode_requested,
        initialRequestedMode,
      );
      const responseModeActual = normalizeModeValue(
        response.mode_actually_used || effectiveReturnedMode,
        responseModeRequested,
      );
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
        documents: normalizeCanvasDocuments(response.documents),
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

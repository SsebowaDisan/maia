import type { ChatResponse } from "../../../../api/client";
import { fallbackAssistantBlocks, normalizeCanvasDocuments, normalizeMessageBlocks } from "../../../messageBlocks";
import { useCanvasStore } from "../../../stores/canvasStore";
import type { AgentActivityEvent, ChatAttachment, ChatTurn } from "../../../types";
import { DEFAULT_PROJECT_ID } from "../../constants";
import { normalizeMindmapMapType, type AgentMode } from "../constants";
import { MODE_SCOPE_STATEMENTS, deriveModeStatus, normalizeModeValue, resolveReturnedTurnMode, type SendConversationMessageParams } from "./common";

type SendLifecycleContext = Pick<
  SendConversationMessageParams,
  | "message"
  | "attachments"
  | "options"
  | "selectedProjectId"
  | "refreshConversations"
  | "setCitationFocus"
  | "setIsSending"
  | "setIsActivityStreaming"
  | "setClarificationPrompt"
  | "setInfoText"
  | "setActivityEvents"
  | "setSelectedTurnIndex"
  | "setChatTurns"
  | "setConversationProjects"
  | "setConversationModes"
  | "setComposerMode"
  | "setSelectedConversationId"
  | "setConversationMindmapSettings"
> & {
  chatTurnsLength: number;
  composerMode: AgentMode;
  mindmapEnabled: boolean;
  mindmapMaxDepth: number;
  mindmapIncludeReasoning: boolean;
  mindmapMapType: string;
};

type SendModeContext = {
  effectiveMode: AgentMode;
  backendMode: AgentMode;
  orchestratorMode: boolean;
  liveStreamMode: boolean;
  webOnlyResearchRequested: boolean;
  requestedTurnMode: ChatTurn["mode"];
  initialRequestedMode: string;
  initialModeStatus: ChatTurn["modeStatus"];
  delayedPendingAssistantMessage: string;
  isFirstTurn: boolean;
  pendingTurnIndex: number;
};

function primePendingTurn(
  context: SendLifecycleContext,
  modeContext: SendModeContext,
  attachments: ChatAttachment[],
): void {
  const { message } = context;
  const { delayedPendingAssistantMessage, requestedTurnMode, initialRequestedMode, initialModeStatus, pendingTurnIndex } =
    modeContext;

  const firstAttachedFile = attachments.find((item) => Boolean(item.fileId));
  if (firstAttachedFile?.fileId) {
    context.setCitationFocus({
      fileId: firstAttachedFile.fileId,
      sourceName: String(firstAttachedFile.name || "Uploaded file"),
      extract: "",
      evidenceId: `send-file-preview-${Date.now()}`,
    });
  }

  context.setIsSending(true);
  context.setIsActivityStreaming(modeContext.liveStreamMode);
  context.setClarificationPrompt(null);
  context.setCitationFocus(null);
  context.setInfoText("");
  context.setActivityEvents([]);
  context.setSelectedTurnIndex(pendingTurnIndex);
  context.setChatTurns((prev) => [
    ...prev,
    {
      user: message,
      assistant: delayedPendingAssistantMessage,
      blocks: fallbackAssistantBlocks(delayedPendingAssistantMessage),
      documents: [],
      plot: null,
      attachments: attachments.length > 0 ? attachments : undefined,
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
}

function applyStreamAssistantPreview(
  setChatTurns: SendConversationMessageParams["setChatTurns"],
  assistant: string,
): void {
  setChatTurns((prev) => {
    const next = [...prev];
    const last = next[next.length - 1];
    next[next.length - 1] = {
      ...(last || {}),
      assistant,
      blocks: fallbackAssistantBlocks(assistant),
    };
    return next;
  });
}

function appendStreamActivity(
  setChatTurns: SendConversationMessageParams["setChatTurns"],
  activityEvents: AgentActivityEvent[],
  delayedPendingAssistantMessage: string,
): void {
  setChatTurns((prev) => {
    const next = [...prev];
    const last = next[next.length - 1];
    next[next.length - 1] = {
      ...(last || {}),
      assistant:
        last && String(last.assistant || "").trim() === delayedPendingAssistantMessage
          ? ""
          : String(last?.assistant || ""),
      activityEvents: [...activityEvents],
    };
    return next;
  });
}

function applyPendingPlot(
  setChatTurns: SendConversationMessageParams["setChatTurns"],
  plot: Record<string, unknown> | null,
): void {
  setChatTurns((prev) => {
    const next = [...prev];
    const last = next[next.length - 1];
    next[next.length - 1] = {
      ...(last || {}),
      plot,
    };
    return next;
  });
}

function applyPendingMode(
  setChatTurns: SendConversationMessageParams["setChatTurns"],
  modeRequested: string,
  modeActuallyUsed: string,
  modeStatus: ChatTurn["modeStatus"],
): void {
  setChatTurns((prev) => {
    const next = [...prev];
    const last = next[next.length - 1];
    next[next.length - 1] = {
      ...(last || {}),
      modeRequested,
      modeActuallyUsed,
      modeStatus,
    };
    return next;
  });
}

function applyPendingHalt(
  setChatTurns: SendConversationMessageParams["setChatTurns"],
  haltReason: string | null,
  haltMessage: string | null,
): void {
  setChatTurns((prev) => {
    const next = [...prev];
    const last = next[next.length - 1];
    next[next.length - 1] = {
      ...(last || {}),
      haltReason,
      haltMessage,
    };
    return next;
  });
}

function applySuccessfulResponse(
  context: SendLifecycleContext,
  modeContext: SendModeContext,
  response: ChatResponse,
  streamedEventsLocal: AgentActivityEvent[],
): void {
  const responseInfoPanel =
    response.info_panel && typeof response.info_panel === "object" && !Array.isArray(response.info_panel)
      ? (response.info_panel as Record<string, unknown>)
      : response.infoPanel && typeof response.infoPanel === "object" && !Array.isArray(response.infoPanel)
        ? (response.infoPanel as Record<string, unknown>)
        : {};
  const responseNextRecommendedSteps = Array.isArray(response.next_recommended_steps)
    ? response.next_recommended_steps
    : [];
  const normalizedResponseDocuments = normalizeCanvasDocuments(response.documents);
  context.setConversationProjects((prev) =>
    prev[response.conversation_id]
      ? prev
      : {
          ...prev,
          [response.conversation_id]: context.selectedProjectId || DEFAULT_PROJECT_ID,
        },
  );
  context.setConversationModes((prev) => ({
    ...prev,
    [response.conversation_id]: modeContext.effectiveMode,
  }));
  context.setComposerMode(modeContext.effectiveMode);
  context.setSelectedConversationId(response.conversation_id);
  context.setConversationMindmapSettings((prev) => ({
    ...prev,
    [response.conversation_id]: {
      enabled: Boolean(context.options?.useMindmap ?? context.mindmapEnabled),
      maxDepth:
        Number((context.options?.mindmapSettings?.["max_depth"] as number) ?? context.mindmapMaxDepth) || 4,
      includeReasoningMap: Boolean(
        (context.options?.mindmapSettings?.["include_reasoning_map"] as boolean) ??
          context.mindmapIncludeReasoning,
      ),
      mapType: normalizeMindmapMapType(context.options?.mindmapSettings?.["map_type"] || context.mindmapMapType),
    },
  }));
  context.setInfoText(response.info || "");

  const effectiveReturnedMode = (response.mode as AgentMode | undefined) || modeContext.backendMode;
  const responseModeRequested =
    modeContext.effectiveMode === "brain"
      ? "brain"
      : normalizeModeValue(response.mode_requested, modeContext.initialRequestedMode);
  const responseModeActual =
    modeContext.effectiveMode === "brain"
      ? "brain"
      : normalizeModeValue(response.mode_actually_used || effectiveReturnedMode, responseModeRequested);
  const resolvedTurnMode = resolveReturnedTurnMode({
    effectiveMode: modeContext.effectiveMode,
    responseMode: effectiveReturnedMode,
    responseModeRequested,
    responseModeActual,
    infoPanel: responseInfoPanel,
    webOnlyResearchRequested: modeContext.webOnlyResearchRequested,
  });
  const backendModeMismatch = modeContext.orchestratorMode && effectiveReturnedMode === "ask";
  const haltReason = String(response.halt_reason || "").trim() || null;
  const haltMessage = String(response.halt_message || "").trim() || null;
  const modeStatus = deriveModeStatus({
    isFirstTurn: modeContext.isFirstTurn,
    requestedMode: responseModeRequested,
    actualMode: responseModeActual,
    existingStatus: null,
    message: haltMessage,
  });
  const finalAssistantText = backendModeMismatch
    ? `${response.answer || ""}\n\n[Notice] Backend is not running orchestrator mode. Restart the API server and try again.`
    : response.answer || "";
  const responseDocumentsForTurn = normalizedResponseDocuments;

  context.setChatTurns((prev) => {
    const next = [...prev];
    const last = next[next.length - 1];
    next[next.length - 1] = {
      ...(last || {}),
      user: context.message,
      assistant: finalAssistantText,
      blocks: normalizeMessageBlocks(response.blocks, finalAssistantText),
      documents: responseDocumentsForTurn,
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
      nextRecommendedSteps: responseNextRecommendedSteps,
      needsHumanReview: Boolean(response.needs_human_review),
      humanReviewNotes: response.human_review_notes || null,
      webSummary: response.web_summary || {},
      infoPanel: responseInfoPanel,
      mindmap: response.mindmap || {},
      activityRunId: response.activity_run_id || null,
      activityEvents: streamedEventsLocal,
    };
    return next;
  });

  if (responseDocumentsForTurn.length > 0) {
    const canvasStore = useCanvasStore.getState();
    canvasStore.upsertDocuments(responseDocumentsForTurn);
    const firstDocument = responseDocumentsForTurn[0];
    if (firstDocument?.id) {
      canvasStore.openDocument(firstDocument.id);
    }
  }
  context.setActivityEvents(streamedEventsLocal);
  context.setSelectedTurnIndex(modeContext.pendingTurnIndex);
}

async function refreshConversationList(
  refreshConversations: SendConversationMessageParams["refreshConversations"],
  setInfoText: SendConversationMessageParams["setInfoText"],
): Promise<void> {
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
}

function applyErrorResponse(
  setChatTurns: SendConversationMessageParams["setChatTurns"],
  message: string,
  errorMessage: string,
  requestedTurnMode: ChatTurn["mode"],
  initialRequestedMode: string,
  initialModeStatus: ChatTurn["modeStatus"],
): void {
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
}

function buildModeContext(
  context: Pick<
    SendConversationMessageParams,
    | "composerMode"
    | "chatTurnsLength"
    | "options"
    | "accessMode"
  >,
): Omit<SendModeContext, "pendingTurnIndex" | "delayedPendingAssistantMessage"> & {
  effectiveAccessMode: ReturnType<typeof resolveAccessMode>;
} {
  const effectiveMode = context.options?.agentMode ?? context.composerMode;
  const backendMode: AgentMode =
    effectiveMode === "brain" ? "company_agent" : effectiveMode;
  const effectiveAccessMode = context.options?.accessMode ?? context.accessMode;
  const orchestratorMode = backendMode === "company_agent" || backendMode === "deep_search";
  const liveStreamMode = orchestratorMode || effectiveMode === "rag";
  const webOnlyResearchRequested =
    backendMode === "deep_search" && Boolean(context.options?.settingOverrides?.["__research_web_only"]);
  const requestedTurnMode: ChatTurn["mode"] =
    effectiveMode === "deep_search" && webOnlyResearchRequested ? "web_search" : effectiveMode;
  const isFirstTurn = context.chatTurnsLength === 0;
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
  return {
    effectiveMode,
    backendMode,
    effectiveAccessMode,
    orchestratorMode,
    liveStreamMode,
    webOnlyResearchRequested,
    requestedTurnMode,
    initialRequestedMode,
    initialModeStatus,
    isFirstTurn,
  };
}

function resolveAccessMode(value: unknown): string {
  return String(value || "restricted");
}

function buildDelayedPendingAssistantMessage(modeContext: Pick<SendModeContext, "liveStreamMode" | "effectiveMode" | "backendMode"> & { webOnlyResearchRequested: boolean }): string {
  if (modeContext.liveStreamMode) {
    if (modeContext.effectiveMode === "brain") {
      return "Brain is assembling your team and running the workflow...";
    }
    if (modeContext.backendMode === "deep_search") {
      return modeContext.webOnlyResearchRequested ? "Running web search..." : "Running deep search...";
    }
    if (modeContext.effectiveMode === "rag") {
      return "Reviewing the selected files and indexed URLs...";
    }
    return "Starting my desktop...";
  }
  if (modeContext.effectiveMode === "rag") {
    return "Grounding the answer in files and indexed URLs already in Maia...";
  }
  return "Thinking....";
}

export {
  applyErrorResponse,
  applyPendingHalt,
  applyPendingMode,
  applyPendingPlot,
  appendStreamActivity,
  applyStreamAssistantPreview,
  applySuccessfulResponse,
  buildDelayedPendingAssistantMessage,
  buildModeContext,
  primePendingTurn,
  refreshConversationList,
};
export type { SendLifecycleContext, SendModeContext };

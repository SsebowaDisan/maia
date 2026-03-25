import { sendChat, type ChatResponse } from "../../../api/client";
import { DEEP_SEARCH_SETTING_OVERRIDES, RAG_SETTING_OVERRIDES } from "./constants";
import type { AgentActivityEvent } from "../../types";
import { SendConversationMessageParams } from "./sendMessageSections/common";
import {
  applyErrorResponse,
  applySuccessfulResponse,
  buildDelayedPendingAssistantMessage,
  buildModeContext,
  primePendingTurn,
  refreshConversationList,
  type SendLifecycleContext,
  type SendModeContext,
} from "./sendMessageSections/state";
import { streamBrainRun, streamChatRun, type SharedPayload } from "./sendMessageSections/streaming";

function buildSharedPayload(
  params: SendConversationMessageParams,
  modeContext: SendModeContext & { effectiveAccessMode: string },
  attachedFileIds: string[],
): SharedPayload {
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

  appendSelection(params.defaultIndexId, attachedFileIds);
  return {
    indexSelection: Object.keys(selectionByIndex).length > 0 ? selectionByIndex : undefined,
    attachments: (params.attachments || [])
      .map((item) => ({
        name: String(item.name || "").trim(),
        fileId: String(item.fileId || "").trim() || undefined,
      }))
      .filter((item) => Boolean(item.name || item.fileId)),
    citation: params.options?.citationMode ?? params.citationMode,
    language: params.options?.language ?? undefined,
    useMindmap: params.options?.useMindmap ?? params.mindmapEnabled,
    mindmapSettings: params.options?.mindmapSettings ?? {
      max_depth: params.mindmapMaxDepth,
      include_reasoning_map: params.mindmapIncludeReasoning,
      map_type: params.mindmapMapType,
    },
    mindmapFocus: params.options?.mindmapFocus ?? {},
    settingOverrides: {
      ...(modeContext.backendMode === "deep_search" ? DEEP_SEARCH_SETTING_OVERRIDES : {}),
      ...(modeContext.effectiveMode === "rag" ? RAG_SETTING_OVERRIDES : {}),
      ...(params.options?.settingOverrides || {}),
      ...(modeContext.effectiveMode === "brain" ? { __brain_mode_enabled: true } : {}),
    },
    agentMode: modeContext.backendMode,
    agentId: params.options?.agentId,
    accessMode: modeContext.effectiveAccessMode,
  };
}

async function sendConversationMessage(params: SendConversationMessageParams) {
  const attachments = params.attachments || [];
  if (!params.message.trim()) {
    return;
  }

  const baseModeContext = buildModeContext(params);
  const modeContext: SendModeContext & { effectiveAccessMode: string } = {
    ...baseModeContext,
    pendingTurnIndex: params.chatTurnsLength,
    delayedPendingAssistantMessage: buildDelayedPendingAssistantMessage(baseModeContext),
  };
  const lifecycleContext: SendLifecycleContext = {
    message: params.message,
    attachments,
    options: params.options,
    selectedProjectId: params.selectedProjectId,
    refreshConversations: params.refreshConversations,
    setCitationFocus: params.setCitationFocus,
    setIsSending: params.setIsSending,
    setIsActivityStreaming: params.setIsActivityStreaming,
    setClarificationPrompt: params.setClarificationPrompt,
    setInfoText: params.setInfoText,
    setActivityEvents: params.setActivityEvents,
    setSelectedTurnIndex: params.setSelectedTurnIndex,
    setChatTurns: params.setChatTurns,
    setConversationProjects: params.setConversationProjects,
    setConversationModes: params.setConversationModes,
    setComposerMode: params.setComposerMode,
    setSelectedConversationId: params.setSelectedConversationId,
    setConversationMindmapSettings: params.setConversationMindmapSettings,
    chatTurnsLength: params.chatTurnsLength,
    composerMode: params.composerMode,
    mindmapEnabled: params.mindmapEnabled,
    mindmapMaxDepth: params.mindmapMaxDepth,
    mindmapIncludeReasoning: params.mindmapIncludeReasoning,
    mindmapMapType: params.mindmapMapType,
  };

  primePendingTurn(lifecycleContext, modeContext, attachments);

  const attachedFileIds = attachments
    .map((item) => item.fileId)
    .filter((item): item is string => Boolean(item));
  const sharedPayload = buildSharedPayload(params, modeContext, attachedFileIds);

  let streamedEventsLocal: AgentActivityEvent[] = [];
  try {
    let response: ChatResponse;
    if (modeContext.liveStreamMode) {
      const streamContext = {
        message: params.message,
        selectedConversationId: params.selectedConversationId,
        setInfoText: params.setInfoText,
        setActivityEvents: params.setActivityEvents,
        setChatTurns: params.setChatTurns,
        setClarificationPrompt: params.setClarificationPrompt,
        effectiveAccessMode: modeContext.effectiveAccessMode,
        effectiveMode: modeContext.effectiveMode,
        isFirstTurn: modeContext.isFirstTurn,
        delayedPendingAssistantMessage: modeContext.delayedPendingAssistantMessage,
        initialRequestedMode: modeContext.initialRequestedMode,
        initialModeStatus: modeContext.initialModeStatus,
      };
      const streamed =
        modeContext.effectiveMode === "brain"
          ? await streamBrainRun(streamContext)
          : await streamChatRun(streamContext, modeContext, sharedPayload);
      response = streamed.response;
      streamedEventsLocal = streamed.streamedEventsLocal;
    } else {
      response = await sendChat(params.message, params.selectedConversationId, sharedPayload);
    }

    applySuccessfulResponse(lifecycleContext, modeContext, response, streamedEventsLocal);
    await refreshConversationList(params.refreshConversations, params.setInfoText);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error || "Unknown request failure");
    applyErrorResponse(
      params.setChatTurns,
      params.message,
      errorMessage,
      modeContext.requestedTurnMode,
      modeContext.initialRequestedMode,
      modeContext.initialModeStatus,
    );
  } finally {
    params.setIsSending(false);
    params.setIsActivityStreaming(false);
  }
}

export { sendConversationMessage };

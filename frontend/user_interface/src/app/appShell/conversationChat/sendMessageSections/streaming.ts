import {
  assembleAndRunWorkflowWithStream,
  createConversation,
  sendChat,
  sendChatStream,
  type ChatResponse,
} from "../../../../api/client";
import { useCanvasStore } from "../../../stores/canvasStore";
import type { AgentActivityEvent, ClarificationPrompt } from "../../../types";
import { extractCanvasDocumentFromToolEvent } from "../../eventHelpers";
import { clarificationPromptFromEvent } from "../clarification";
import { asRecord, deriveModeStatus, isAgentActivityPayload, normalizeModeValue, type SendConversationMessageParams } from "./common";
import { applyPendingHalt, applyPendingMode, applyPendingPlot, appendStreamActivity, applyStreamAssistantPreview, type SendModeContext } from "./state";
import { summarizeBrainRun, toActivityEventFromWorkflowEvent } from "./workflow";

type StreamExecutionResult = {
  response: ChatResponse;
  streamedEventsLocal: AgentActivityEvent[];
};

type SharedPayload = {
  indexSelection?: Record<string, { mode: "select"; file_ids: string[] }>;
  attachments: { name: string; fileId?: string }[];
  citation: string;
  language?: string;
  useMindmap: boolean;
  mindmapSettings: Record<string, unknown>;
  mindmapFocus: Record<string, unknown>;
  settingOverrides: Record<string, unknown>;
  agentMode: string;
  agentId?: string;
  accessMode: string;
};

type StreamContext = Pick<
  SendConversationMessageParams,
  | "message"
  | "selectedConversationId"
  | "setInfoText"
  | "setActivityEvents"
  | "setChatTurns"
  | "setClarificationPrompt"
> & {
  effectiveAccessMode: string;
  effectiveMode: SendModeContext["effectiveMode"];
  isFirstTurn: boolean;
  delayedPendingAssistantMessage: string;
  initialRequestedMode: string;
  initialModeStatus: SendModeContext["initialModeStatus"];
};

async function streamBrainRun(context: StreamContext): Promise<StreamExecutionResult> {
  const streamedEvents: AgentActivityEvent[] = [];
  let streamedRunId = "";
  let brainEventIndex = 0;
  const fallbackRunId = `brain_${Date.now()}`;
  await assembleAndRunWorkflowWithStream(context.message, {
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
      context.setActivityEvents([...streamedEvents]);
      const liveAssistant = normalized.detail ? `${normalized.title}\n${normalized.detail}` : normalized.title;
      applyStreamAssistantPreview(context.setChatTurns, liveAssistant || "");
    },
  });

  let ensuredConversationId = String(context.selectedConversationId || "").trim();
  if (!ensuredConversationId) {
    const created = await createConversation();
    ensuredConversationId = String(created.id || "").trim();
  }
  if (!ensuredConversationId) {
    throw new Error("Unable to resolve a conversation for Brain mode.");
  }

  const answer = summarizeBrainRun(streamedEvents);
  const modeStatus = deriveModeStatus({
    isFirstTurn: context.isFirstTurn,
    requestedMode: "brain",
    actualMode: "brain",
    existingStatus: context.initialModeStatus,
    message: null,
  });
  applyPendingMode(context.setChatTurns, "brain", "brain", modeStatus);

  return {
    streamedEventsLocal: [...streamedEvents],
    response: {
      conversation_id: ensuredConversationId,
      conversation_name: "Brain run",
      message: context.message,
      answer,
      blocks: [{ type: "markdown", markdown: answer }],
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
    },
  };
}

async function streamChatRun(
  context: StreamContext,
  modeContext: SendModeContext,
  sharedPayload: SharedPayload,
): Promise<StreamExecutionResult> {
  let streamedInfo = "";
  const streamedEvents: AgentActivityEvent[] = [];
  let streamedRunId = "";
  let streamedModeRequested = context.initialRequestedMode;
  let streamedModeActual = context.initialRequestedMode;
  let streamedModeStatus = context.initialModeStatus;
  let streamedHaltReason: string | null = null;
  let streamedHaltMessage: string | null = null;

  try {
    const response = await sendChatStream(context.message, context.selectedConversationId, {
      ...sharedPayload,
      agentGoal: context.message,
      idleTimeoutMs: modeContext.effectiveMode === "rag" ? 90000 : 60000,
      onEvent: (event) => {
        if (!event || typeof event !== "object") {
          return;
        }
        if (event.type === "chat_delta") {
          applyStreamAssistantPreview(context.setChatTurns, String(event.text || ""));
          return;
        }
        if (event.type === "info_delta") {
          streamedInfo += String(event.delta || "");
          context.setInfoText(streamedInfo);
          return;
        }
        if (event.type === "plot") {
          const plotPayload =
            event.plot && typeof event.plot === "object"
              ? (event.plot as Record<string, unknown>)
              : null;
          applyPendingPlot(context.setChatTurns, plotPayload);
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
              String(event.scope_statement || "").trim() || modeContext.initialModeStatus?.scopeStatement || null,
            message: String(event.message || "").trim() || null,
          };
          applyPendingMode(context.setChatTurns, streamedModeRequested, streamedModeActual, streamedModeStatus);
          return;
        }
        if (event.type === "mode_downgraded") {
          streamedModeRequested = normalizeModeValue(
            event.requested_mode,
            streamedModeRequested || context.initialRequestedMode,
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
          applyPendingMode(context.setChatTurns, streamedModeRequested, streamedModeActual, streamedModeStatus);
          return;
        }
        if (event.type === "halt") {
          streamedHaltReason = String(event.reason || "").trim() || null;
          streamedHaltMessage = String(event.message || "").trim() || null;
          applyPendingHalt(context.setChatTurns, streamedHaltReason, streamedHaltMessage);
          return;
        }
        if (event.type !== "activity" || !event.event || !isAgentActivityPayload(event.event)) {
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
          originalRequest: context.message,
          agentMode: modeContext.effectiveMode,
          accessMode: context.effectiveAccessMode as "restricted" | "full_access",
        });
        if (detectedPrompt) {
          context.setClarificationPrompt((previous: ClarificationPrompt | null) => {
            if (previous?.runId && previous.runId === detectedPrompt.runId) {
              return previous;
            }
            return detectedPrompt;
          });
        }
        streamedEvents.push(payload);
        context.setActivityEvents([...streamedEvents]);
        appendStreamActivity(context.setChatTurns, streamedEvents, context.delayedPendingAssistantMessage);
      },
    });

    streamedModeRequested = normalizeModeValue(response.mode_requested, streamedModeRequested || context.initialRequestedMode);
    streamedModeActual = normalizeModeValue(
      response.mode_actually_used || response.mode,
      streamedModeActual || streamedModeRequested || "ask",
    );
    streamedHaltReason = String(response.halt_reason || streamedHaltReason || "").trim() || null;
    streamedHaltMessage = String(response.halt_message || streamedHaltMessage || "").trim() || null;
    streamedModeStatus = deriveModeStatus({
      isFirstTurn: context.isFirstTurn,
      requestedMode: streamedModeRequested,
      actualMode: streamedModeActual,
      existingStatus: streamedModeStatus,
      message: streamedModeStatus?.message || streamedHaltMessage || null,
    });
    applyPendingMode(context.setChatTurns, streamedModeRequested, streamedModeActual, streamedModeStatus);
    applyPendingHalt(context.setChatTurns, streamedHaltReason, streamedHaltMessage);

    return {
      response,
      streamedEventsLocal: [...streamedEvents],
    };
  } catch (streamError) {
    const response = await sendChat(context.message, context.selectedConversationId, {
      ...sharedPayload,
      agentGoal: context.message,
    });
    context.setActivityEvents([]);
    context.setInfoText((previous) =>
      previous
        ? `${previous}\n\n[Notice] Live activity stream timed out. Used direct response fallback.`
        : "[Notice] Live activity stream timed out. Used direct response fallback.",
    );
    console.warn("Orchestrator stream fallback triggered:", streamError);
    return { response, streamedEventsLocal: [] };
  }
}

export { streamBrainRun, streamChatRun };
export type { SharedPayload, StreamExecutionResult, StreamContext };

import type { Dispatch, SetStateAction } from "react";
import { normalizeMindmapMapType, type AgentMode, type ConversationMindmapSettings, type SendMessageOptions } from "../conversationChat/constants";
import type { AgentActivityEvent, ChatTurn, ClarificationPrompt } from "../../types";
import { DEFAULT_PROJECT_ID } from "../constants";
import {
  createConversation,
  deleteConversation,
  getAgentRunEvents,
  getConversation,
  listConversations,
  updateConversation,
} from "../../../api/client";
import { buildConversationTurns, extractAgentEvents } from "../eventHelpers";
import { sendConversationMessage } from "../conversationChat/sendMessage";
import { getActiveProjectId, getCachedConversationSnapshot } from "./common";
import type { SidebarProject } from "../types";

function applyConversationState(params: {
  conversationId: string;
  turns: ChatTurn[];
  mode: AgentMode;
  preferredTurnIndex?: number | null;
  fallbackInfoText?: string;
  conversationMindmapSettings: Record<string, ConversationMindmapSettings>;
  setChatTurns: Dispatch<SetStateAction<ChatTurn[]>>;
  setComposerMode: Dispatch<SetStateAction<AgentMode>> | ((value: AgentMode) => void);
  setMindmapEnabled: (value: boolean) => void;
  setMindmapMaxDepth: (value: number) => void;
  setMindmapIncludeReasoning: (value: boolean) => void;
  setMindmapMapType: (value: "structure" | "evidence" | "work_graph" | "context_mindmap") => void;
  setSelectedTurnIndex: (value: number | null) => void;
  setInfoText: (value: string) => void;
  setActivityEvents: (value: AgentActivityEvent[]) => void;
}) {
  const {
    conversationId,
    turns,
    mode,
    preferredTurnIndex,
    fallbackInfoText = "",
    conversationMindmapSettings,
    setChatTurns,
    setComposerMode,
    setMindmapEnabled,
    setMindmapMaxDepth,
    setMindmapIncludeReasoning,
    setMindmapMapType,
    setSelectedTurnIndex,
    setInfoText,
    setActivityEvents,
  } = params;

  setChatTurns(turns);
  setComposerMode(mode);
  const mapSettings = conversationMindmapSettings[conversationId];
  if (mapSettings) {
    setMindmapEnabled(Boolean(mapSettings.enabled));
    setMindmapMaxDepth(Math.max(2, Math.min(8, Number(mapSettings.maxDepth || 4))));
    setMindmapIncludeReasoning(Boolean(mapSettings.includeReasoningMap));
    setMindmapMapType(normalizeMindmapMapType(mapSettings.mapType));
  } else {
    setMindmapEnabled(true);
    setMindmapMaxDepth(4);
    setMindmapIncludeReasoning(true);
    setMindmapMapType("structure");
  }

  if (!turns.length) {
    setSelectedTurnIndex(null);
    setInfoText("");
    setActivityEvents([]);
    return;
  }

  const requestedIndex = Number(preferredTurnIndex);
  const safeIndex =
    Number.isFinite(requestedIndex) && requestedIndex >= 0 && requestedIndex < turns.length
      ? requestedIndex
      : turns.length - 1;
  setSelectedTurnIndex(safeIndex);
  setInfoText(turns[safeIndex]?.info || fallbackInfoText || "");
  setActivityEvents(turns[safeIndex]?.activityEvents || []);
}

function resetConversationDetail(params: {
  setChatTurns: Dispatch<SetStateAction<ChatTurn[]>>;
  setSelectedTurnIndex: (value: number | null) => void;
  setInfoText: (value: string) => void;
  setActivityEvents: (value: AgentActivityEvent[]) => void;
}) {
  params.setChatTurns([]);
  params.setSelectedTurnIndex(null);
  params.setInfoText("");
  params.setActivityEvents([]);
}

async function refreshConversations(setConversations: Dispatch<SetStateAction<any[]>>) {
  const items = await listConversations();
  setConversations(items);
}

async function selectConversation(params: {
  conversationId: string;
  conversationDetailCacheStorageKey: string;
  conversationModes: Record<string, AgentMode>;
  conversationMindmapSettings: Record<string, ConversationMindmapSettings>;
  selectedConversationIdRef: { current: string | null };
  selectedTurnIndexRef: { current: number | null };
  setSelectedConversationId: (value: string) => void;
  setChatTurns: Dispatch<SetStateAction<ChatTurn[]>>;
  setComposerMode: (value: AgentMode) => void;
  setMindmapEnabled: (value: boolean) => void;
  setMindmapMaxDepth: (value: number) => void;
  setMindmapIncludeReasoning: (value: boolean) => void;
  setMindmapMapType: (value: "structure" | "evidence" | "work_graph" | "context_mindmap") => void;
  setSelectedTurnIndex: (value: number | null) => void;
  setInfoText: (value: string) => void;
  setActivityEvents: (value: AgentActivityEvent[]) => void;
  refreshConversations: () => Promise<void>;
}) {
  params.setSelectedConversationId(params.conversationId);
  const cachedSnapshot = getCachedConversationSnapshot(
    params.conversationDetailCacheStorageKey,
    params.conversationId,
  );
  const savedMode = params.conversationModes[params.conversationId] || cachedSnapshot?.composerMode || "ask";
  if (cachedSnapshot) {
    applyConversationState({
      conversationId: params.conversationId,
      turns: cachedSnapshot.turns || [],
      mode: savedMode,
      preferredTurnIndex: cachedSnapshot.selectedTurnIndex,
      fallbackInfoText: cachedSnapshot.infoText,
      conversationMindmapSettings: params.conversationMindmapSettings,
      setChatTurns: params.setChatTurns,
      setComposerMode: params.setComposerMode,
      setMindmapEnabled: params.setMindmapEnabled,
      setMindmapMaxDepth: params.setMindmapMaxDepth,
      setMindmapIncludeReasoning: params.setMindmapIncludeReasoning,
      setMindmapMapType: params.setMindmapMapType,
      setSelectedTurnIndex: params.setSelectedTurnIndex,
      setInfoText: params.setInfoText,
      setActivityEvents: params.setActivityEvents,
    });
  }

  try {
    const detail = await getConversation(params.conversationId);
    const { turns, runIds } = buildConversationTurns(detail);
    const baseTurns = turns.map((turn) => ({ ...turn, activityEvents: turn.activityEvents || [] }));
    applyConversationState({
      conversationId: params.conversationId,
      turns: baseTurns,
      mode: savedMode,
      preferredTurnIndex: cachedSnapshot?.selectedTurnIndex,
      fallbackInfoText: cachedSnapshot?.infoText || "",
      conversationMindmapSettings: params.conversationMindmapSettings,
      setChatTurns: params.setChatTurns,
      setComposerMode: params.setComposerMode,
      setMindmapEnabled: params.setMindmapEnabled,
      setMindmapMaxDepth: params.setMindmapMaxDepth,
      setMindmapIncludeReasoning: params.setMindmapIncludeReasoning,
      setMindmapMapType: params.setMindmapMapType,
      setSelectedTurnIndex: params.setSelectedTurnIndex,
      setInfoText: params.setInfoText,
      setActivityEvents: params.setActivityEvents,
    });

    if (runIds.length > 0) {
      void Promise.all(
        runIds.map(async (runId) => {
          try {
            const rows = await getAgentRunEvents(runId);
            return [runId, extractAgentEvents(rows)] as const;
          } catch {
            return [runId, [] as AgentActivityEvent[]] as const;
          }
        }),
      ).then((entries) => {
        if (params.selectedConversationIdRef.current !== params.conversationId) {
          return;
        }
        const runEventsMap = Object.fromEntries(entries);
        const hydratedTurns = baseTurns.map((turn) =>
          turn.activityRunId ? { ...turn, activityEvents: runEventsMap[turn.activityRunId] || [] } : turn,
        );
        params.setChatTurns(hydratedTurns);
        const activeIndex = params.selectedTurnIndexRef.current;
        if (
          Number.isFinite(activeIndex) &&
          activeIndex !== null &&
          activeIndex >= 0 &&
          activeIndex < hydratedTurns.length
        ) {
          params.setActivityEvents(hydratedTurns[activeIndex]?.activityEvents || []);
        }
      });
    }
  } catch (error) {
    const reason =
      error instanceof Error && error.message.trim().length > 0
        ? error.message.trim()
        : "This chat could not be loaded from the server.";
    if (!cachedSnapshot) {
      resetConversationDetail({
        setChatTurns: params.setChatTurns,
        setSelectedTurnIndex: params.setSelectedTurnIndex,
        setInfoText: params.setInfoText,
        setActivityEvents: params.setActivityEvents,
      });
    }
    params.setInfoText(`Unable to open this chat right now. ${reason}`);
    void params.refreshConversations().catch(() => undefined);
  }
}

async function createConversationForProject(params: {
  preferredProjectId?: string;
  projects: SidebarProject[];
  selectedProjectId: string;
  composerMode: AgentMode;
  setSelectedProjectId: (projectId: string) => void;
  setConversationProjects: Dispatch<SetStateAction<Record<string, string>>>;
  setConversationModes: Dispatch<SetStateAction<Record<string, AgentMode>>>;
  setSelectedConversationId: (value: string) => void;
  resetConversationDetail: () => void;
  refreshConversations: () => Promise<void>;
  setInfoText: (value: string) => void;
}) {
  const activeProjectId = getActiveProjectId(
    params.preferredProjectId,
    params.selectedProjectId,
    params.projects,
  );
  if (activeProjectId !== params.selectedProjectId) {
    params.setSelectedProjectId(activeProjectId);
  }

  try {
    const created = await createConversation();
    params.setConversationProjects((prev) => ({ ...prev, [created.id]: activeProjectId }));
    params.setConversationModes((prev) => ({ ...prev, [created.id]: params.composerMode }));
    params.setSelectedConversationId(created.id);
    params.resetConversationDetail();
    await params.refreshConversations();
  } catch (error) {
    params.setInfoText(`Failed to create a new conversation: ${String(error)}`);
  }
}

async function renameConversation(conversationId: string, name: string, refreshConversationsFn: () => Promise<void>) {
  const normalizedName = name.trim();
  if (!normalizedName) {
    return;
  }
  await updateConversation(conversationId, { name: normalizedName });
  await refreshConversationsFn();
}

async function deleteConversationWithState(params: {
  conversationId: string;
  selectedConversationId: string | null;
  setConversationProjects: Dispatch<SetStateAction<Record<string, string>>>;
  setConversationModes: Dispatch<SetStateAction<Record<string, AgentMode>>>;
  setSelectedConversationId: (value: string | null) => void;
  resetConversationDetail: () => void;
  refreshConversations: () => Promise<void>;
}) {
  await deleteConversation(params.conversationId);
  params.setConversationProjects((prev) => {
    const next = { ...prev };
    delete next[params.conversationId];
    return next;
  });
  params.setConversationModes((prev) => {
    const next = { ...prev };
    delete next[params.conversationId];
    return next;
  });
  if (params.selectedConversationId === params.conversationId) {
    params.setSelectedConversationId(null);
    params.resetConversationDetail();
  }
  await params.refreshConversations();
}

async function sendConversationMessageFromHook(params: {
  message: string;
  attachments?: ChatTurn["attachments"];
  options?: SendMessageOptions;
  composerMode: AgentMode;
  accessMode: "restricted" | "full_access";
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
  setCitationFocus: (value: any) => void;
  setIsSending: (value: boolean) => void;
  setIsActivityStreaming: (value: boolean) => void;
  setClarificationPrompt: (value: any) => void;
  setInfoText: (value: any) => void;
  setActivityEvents: (value: AgentActivityEvent[]) => void;
  setSelectedTurnIndex: (value: number | null) => void;
  setChatTurns: Dispatch<SetStateAction<ChatTurn[]>>;
  setConversationProjects: Dispatch<SetStateAction<Record<string, string>>>;
  setConversationModes: Dispatch<SetStateAction<Record<string, AgentMode>>>;
  setComposerMode: (value: AgentMode) => void;
  setSelectedConversationId: (value: string) => void;
  setConversationMindmapSettings: Dispatch<SetStateAction<Record<string, ConversationMindmapSettings>>>;
}) {
  await sendConversationMessage(params as any);
}

function buildClarificationContinuation(snapshot: ClarificationPrompt, answers: string[]) {
  const rows = snapshot.questions.length ? snapshot.questions : snapshot.missingRequirements;
  const answeredRows = rows
    .map((row, index) => {
      const answer = String(answers[index] || "").trim();
      if (!answer) {
        return "";
      }
      return `- ${row}: ${answer}`;
    })
    .filter((item) => item.length > 0);
  if (!answeredRows.length) {
    throw new Error("Provide the required clarification details before continuing.");
  }

  const continuationMessage = [
    `Continue the paused task from run ${snapshot.runId || "previous run"}.`,
    `Original request: ${snapshot.originalRequest}`,
    "Clarification details:",
    ...answeredRows,
    "Proceed with execution now and complete the requested actions.",
  ].join("\n");

  return { answeredRows, continuationMessage };
}

function syncFallbackProject(params: {
  conversations: Array<{ id: string }>;
  visibleConversationsLength: number;
  conversationProjects: Record<string, string>;
  selectedProjectId: string;
  setSelectedProjectId: (projectId: string) => void;
}) {
  if (!params.conversations.length || params.visibleConversationsLength > 0) {
    return;
  }
  const fallbackConversation = params.conversations[0];
  if (!fallbackConversation) {
    return;
  }
  const fallbackProjectId = params.conversationProjects[fallbackConversation.id] || DEFAULT_PROJECT_ID;
  if (fallbackProjectId !== params.selectedProjectId) {
    params.setSelectedProjectId(fallbackProjectId);
  }
}

function hydrateInitialConversation(params: {
  selectedConversationId: string | null;
  initialConversationHydrated: boolean;
  conversationsLength: number;
  visibleConversations: Array<{ id: string }>;
  lastConversationStorageKey: string;
  handleSelectConversation: (conversationId: string) => Promise<void>;
  setInitialConversationHydrated: (value: boolean) => void;
}) {
  if (params.selectedConversationId && !params.initialConversationHydrated) {
    params.setInitialConversationHydrated(true);
    void params.handleSelectConversation(params.selectedConversationId).catch(() => undefined);
    return;
  }
  if (!params.conversationsLength || params.initialConversationHydrated || params.selectedConversationId) {
    return;
  }
  if (!params.visibleConversations.length) {
    return;
  }
  const storedConversationId = localStorage.getItem(params.lastConversationStorageKey)?.trim() || "";
  const visibleIds = new Set(params.visibleConversations.map((item) => item.id));
  const candidateConversationId = visibleIds.has(storedConversationId)
    ? storedConversationId
    : params.visibleConversations[0].id;
  if (!candidateConversationId) {
    params.setInitialConversationHydrated(true);
    return;
  }
  params.setInitialConversationHydrated(true);
  void params.handleSelectConversation(candidateConversationId).catch(() => undefined);
}

export {
  applyConversationState,
  buildClarificationContinuation,
  createConversationForProject,
  deleteConversationWithState,
  hydrateInitialConversation,
  refreshConversations,
  renameConversation,
  resetConversationDetail,
  selectConversation,
  sendConversationMessageFromHook,
  syncFallbackProject,
};

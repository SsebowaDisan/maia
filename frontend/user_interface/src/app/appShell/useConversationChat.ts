import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ACTIVE_USER_ID } from "../../api/client/core";
import { getAgentRunEvents, type ConversationSummary } from "../../api/client";
import { DEFAULT_PROJECT_ID } from "./constants";
import type { SidebarProject } from "./types";
import type { AgentActivityEvent, ChatTurn, CitationFocus, ClarificationPrompt } from "../types";
import {
  MINDMAP_SETTINGS_STORAGE_KEY,
  type AccessMode,
  type AgentMode,
  type ConversationMindmapSettings,
  type MindmapMapType,
  type SendMessageOptions,
} from "./conversationChat/constants";
import { buildConversationTurns, extractAgentEvents } from "./eventHelpers";
import {
  buildClarificationContinuation,
  createConversationForProject,
  deleteConversationWithState,
  hydrateInitialConversation,
  refreshConversations as refreshConversationsAction,
  renameConversation,
  resetConversationDetail,
  selectConversation,
  sendConversationMessageFromHook,
  syncFallbackProject,
} from "./useConversationChatSections/actions";
import {
  getInitialConversationCache,
  readStoredMindmapSettings,
  readStoredJson,
  storageScopeForUser,
  stripTurnActivityForCache,
  type CachedConversationSnapshot,
  type UseConversationChatParams,
} from "./useConversationChatSections/common";

export function useConversationChat({
  projects,
  selectedProjectId,
  setSelectedProjectId,
  conversationProjects,
  setConversationProjects,
  conversationModes,
  setConversationModes,
  defaultIndexId,
}: UseConversationChatParams) {
  const userStorageScope = storageScopeForUser(ACTIVE_USER_ID);
  const mindmapSettingsStorageKey = `${MINDMAP_SETTINGS_STORAGE_KEY}:${userStorageScope}`;
  const {
    cachedConversationId,
    initialCachedSnapshot,
    conversationsCacheStorageKey,
    conversationDetailCacheStorageKey,
    lastConversationStorageKey,
  } = getInitialConversationCache(userStorageScope);

  const [conversations, setConversations] = useState<ConversationSummary[]>(() =>
    readStoredJson<ConversationSummary[]>(conversationsCacheStorageKey, []),
  );
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(cachedConversationId);
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>(() =>
    initialCachedSnapshot?.turns ?? [],
  );
  const [selectedTurnIndex, setSelectedTurnIndex] = useState<number | null>(() =>
    initialCachedSnapshot?.selectedTurnIndex ?? null,
  );
  const [infoText, setInfoText] = useState(() =>
    initialCachedSnapshot?.infoText ?? "",
  );
  const [citationMode, setCitationMode] = useState("inline");
  const [mindmapEnabled, setMindmapEnabled] = useState(true);
  const [mindmapMaxDepth, setMindmapMaxDepth] = useState(4);
  const [mindmapIncludeReasoning, setMindmapIncludeReasoning] = useState(true);
  const [mindmapMapType, setMindmapMapType] = useState<MindmapMapType>("structure");
  const [conversationMindmapSettings, setConversationMindmapSettings] = useState<
    Record<string, ConversationMindmapSettings>
  >(() => readStoredMindmapSettings(mindmapSettingsStorageKey, MINDMAP_SETTINGS_STORAGE_KEY));
  const [citationFocus, setCitationFocus] = useState<CitationFocus | null>(null);
  const [composerMode, setComposerMode] = useState<AgentMode>(() =>
    (initialCachedSnapshot?.composerMode as AgentMode) || "ask",
  );
  const [accessMode, setAccessMode] = useState<AccessMode>("restricted");
  const [activityEvents, setActivityEvents] = useState<AgentActivityEvent[]>([]);
  const [isActivityStreaming, setIsActivityStreaming] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [clarificationPrompt, setClarificationPrompt] = useState<ClarificationPrompt | null>(null);
  const [initialConversationHydrated, setInitialConversationHydrated] = useState(false);
  const selectedConversationIdRef = useRef<string | null>(selectedConversationId);
  const selectedTurnIndexRef = useRef<number | null>(selectedTurnIndex);

  const visibleConversations = useMemo(
    () =>
      conversations.filter(
        (conversation) =>
          (conversationProjects[conversation.id] || DEFAULT_PROJECT_ID) === selectedProjectId,
      ),
    [conversations, conversationProjects, selectedProjectId],
  );

  const refreshConversations = useCallback(
    async () => refreshConversationsAction(setConversations),
    [],
  );

  const resetConversationDetailState = useCallback(() => {
    resetConversationDetail({ setChatTurns, setSelectedTurnIndex, setInfoText, setActivityEvents });
  }, []);

  useEffect(() => {
    if (!selectedConversationId) {
      return;
    }
    const selectedConversationProject = conversationProjects[selectedConversationId] || DEFAULT_PROJECT_ID;
    if (selectedConversationProject !== selectedProjectId) {
      setSelectedConversationId(null);
      resetConversationDetailState();
    }
  }, [conversationProjects, resetConversationDetailState, selectedConversationId, selectedProjectId]);

  useEffect(() => {
    selectedConversationIdRef.current = selectedConversationId;
  }, [selectedConversationId]);

  useEffect(() => {
    selectedTurnIndexRef.current = selectedTurnIndex;
  }, [selectedTurnIndex]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(mindmapSettingsStorageKey, JSON.stringify(conversationMindmapSettings));
  }, [conversationMindmapSettings, mindmapSettingsStorageKey]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      window.localStorage.setItem(conversationsCacheStorageKey, JSON.stringify(conversations));
    } catch {
      // Keep the UI responsive even if cache persistence fails.
    }
  }, [conversations, conversationsCacheStorageKey]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    if (selectedConversationId) {
      window.localStorage.setItem(lastConversationStorageKey, selectedConversationId);
      return;
    }
    window.localStorage.removeItem(lastConversationStorageKey);
  }, [lastConversationStorageKey, selectedConversationId]);

  useEffect(() => {
    if (typeof window === "undefined" || !selectedConversationId) {
      return;
    }
    try {
      const nextSnapshot: CachedConversationSnapshot = {
        turns: stripTurnActivityForCache(chatTurns),
        selectedTurnIndex,
        infoText,
        composerMode,
      };
      const existing = readStoredJson<Record<string, CachedConversationSnapshot>>(
        conversationDetailCacheStorageKey,
        {},
      );
      window.localStorage.setItem(
        conversationDetailCacheStorageKey,
        JSON.stringify({
          ...existing,
          [selectedConversationId]: nextSnapshot,
        }),
      );
    } catch {
      // Do not block interaction on cache write failures.
    }
  }, [
    chatTurns,
    composerMode,
    conversationDetailCacheStorageKey,
    infoText,
    selectedConversationId,
    selectedTurnIndex,
  ]);

  const handleSelectConversation = useCallback(
    async (conversationId: string) => {
      await selectConversation({
        conversationId,
        conversationDetailCacheStorageKey,
        conversationModes,
        conversationMindmapSettings,
        selectedConversationIdRef,
        selectedTurnIndexRef,
        setSelectedConversationId,
        setChatTurns,
        setComposerMode,
        setMindmapEnabled,
        setMindmapMaxDepth,
        setMindmapIncludeReasoning,
        setMindmapMapType,
        setSelectedTurnIndex,
        setInfoText,
        setActivityEvents,
        refreshConversations,
      });
    },
    [conversationDetailCacheStorageKey, conversationModes, conversationMindmapSettings, refreshConversations],
  );

  const handleCreateConversation = useCallback(
    async (preferredProjectId?: string) => {
      await createConversationForProject({
        preferredProjectId,
        projects,
        selectedProjectId,
        composerMode,
        setSelectedProjectId,
        setConversationProjects,
        setConversationModes,
        setSelectedConversationId,
        resetConversationDetail: resetConversationDetailState,
        refreshConversations,
        setInfoText,
      });
    },
    [
      composerMode,
      projects,
      refreshConversations,
      resetConversationDetailState,
      selectedProjectId,
      setConversationModes,
      setConversationProjects,
      setSelectedProjectId,
    ],
  );

  const handleRenameConversation = useCallback(
    async (conversationId: string, name: string) => {
      await renameConversation(conversationId, name, refreshConversations);
    },
    [refreshConversations],
  );

  const handleDeleteConversation = useCallback(
    async (conversationId: string) => {
      await deleteConversationWithState({
        conversationId,
        selectedConversationId,
        setConversationProjects,
        setConversationModes,
        setSelectedConversationId,
        resetConversationDetail: resetConversationDetailState,
        refreshConversations,
      });
    },
    [
      refreshConversations,
      resetConversationDetailState,
      selectedConversationId,
      setConversationModes,
      setConversationProjects,
    ],
  );

  const handleSendMessage = useCallback(
    async (message: string, attachments?: ChatTurn["attachments"], options?: SendMessageOptions) => {
      await sendConversationMessageFromHook({
        message,
        attachments,
        options,
        composerMode,
        accessMode,
        chatTurnsLength: chatTurns.length,
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
      });
    },
    [
      accessMode,
      chatTurns.length,
      citationMode,
      composerMode,
      defaultIndexId,
      mindmapEnabled,
      mindmapIncludeReasoning,
      mindmapMaxDepth,
      mindmapMapType,
      refreshConversations,
      selectedConversationId,
      selectedProjectId,
      setConversationModes,
      setConversationProjects,
    ],
  );

  useEffect(() => {
    syncFallbackProject({
      conversations,
      visibleConversationsLength: visibleConversations.length,
      conversationProjects,
      selectedProjectId,
      setSelectedProjectId,
    });
  }, [conversationProjects, conversations, selectedProjectId, setSelectedProjectId, visibleConversations.length]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    hydrateInitialConversation({
      selectedConversationId,
      initialConversationHydrated,
      handleSelectConversation,
      setInitialConversationHydrated,
    });
  }, [
    handleSelectConversation,
    initialConversationHydrated,
    selectedConversationId,
  ]);

  const handleUpdateUserTurn = useCallback((turnIndex: number, message: string) => {
    setChatTurns((prev) => prev.map((turn, idx) => (idx === turnIndex ? { ...turn, user: message } : turn)));
  }, []);

  const handleSelectTurn = useCallback((turnIndex: number) => {
    setSelectedTurnIndex(turnIndex);
    setInfoText(chatTurns[turnIndex]?.info || "");
    const selected = chatTurns[turnIndex];
    if (selected?.activityEvents && selected.activityEvents.length > 0) {
      setActivityEvents(selected.activityEvents);
      return;
    }
    if (selected?.activityRunId) {
      void getAgentRunEvents(selected.activityRunId)
        .then((rows) => {
          const events = extractAgentEvents(rows);
          setActivityEvents(events);
          setChatTurns((prev) =>
            prev.map((turn, index) => (index === turnIndex ? { ...turn, activityEvents: events } : turn)),
          );
        })
        .catch(() => setActivityEvents([]));
      return;
    }
    setActivityEvents([]);
  }, [chatTurns]);

  const handleAgentModeChange = useCallback(
    (mode: AgentMode) => {
      setComposerMode(mode);
      if (selectedConversationId) {
        setConversationModes((prev) => ({
          ...prev,
          [selectedConversationId]: mode,
        }));
      }
    },
    [selectedConversationId, setConversationModes],
  );

  useEffect(() => {
    if (!selectedConversationId) {
      return;
    }
    setConversationMindmapSettings((prev) => ({
      ...prev,
      [selectedConversationId]: {
        enabled: mindmapEnabled,
        maxDepth: mindmapMaxDepth,
        includeReasoningMap: mindmapIncludeReasoning,
        mapType: mindmapMapType,
      },
    }));
  }, [mindmapEnabled, mindmapIncludeReasoning, mindmapMapType, mindmapMaxDepth, selectedConversationId]);

  return {
    accessMode,
    activityEvents,
    chatTurns,
    citationFocus,
    citationMode,
    composerMode,
    conversations,
    clarificationPrompt,
    dismissClarificationPrompt: () => setClarificationPrompt(null),
    handleAgentModeChange,
    handleCreateConversation,
    handleDeleteConversation,
    handleRenameConversation,
    handleSelectConversation,
    handleSelectTurn,
    handleSendMessage,
    handleUpdateUserTurn,
    infoText,
    isActivityStreaming,
    isSending,
    mindmapEnabled,
    mindmapIncludeReasoning,
    mindmapMapType,
    mindmapMaxDepth,
    refreshConversations,
    selectedConversationId,
    selectedTurnIndex,
    setAccessMode,
    setCitationFocus,
    setCitationMode,
    setComposerMode,
    setInfoText,
    setMindmapEnabled,
    setMindmapIncludeReasoning,
    setMindmapMapType,
    setMindmapMaxDepth,
    submitClarificationPrompt: async (answers: string[]) => {
      if (!clarificationPrompt) {
        return;
      }
      const { answeredRows, continuationMessage } = buildClarificationContinuation(clarificationPrompt, answers);
      const snapshot = clarificationPrompt;
      setClarificationPrompt(null);
      try {
        await handleSendMessage(continuationMessage, undefined, {
          agentMode: snapshot.agentMode,
          accessMode: snapshot.accessMode,
          settingOverrides: {
            __clarification_resume: true,
            __clarification_answers: answeredRows,
          },
        });
      } catch (error) {
        setClarificationPrompt(snapshot);
        throw error;
      }
    },
    visibleConversations,
  };
}

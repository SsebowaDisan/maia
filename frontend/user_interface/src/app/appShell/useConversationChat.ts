import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { ACTIVE_USER_ID } from "../../api/client/core";
import {
  createConversation,
  deleteConversation,
  getAgentRunEvents,
  getConversation,
  listConversations,
  updateConversation,
  type ConversationSummary,
} from "../../api/client";
import { buildConversationTurns, extractAgentEvents } from "./eventHelpers";
import { DEFAULT_PROJECT_ID } from "./constants";
import type { SidebarProject } from "./types";
import type {
  AgentActivityEvent,
  ChatTurn,
  CitationFocus,
  ClarificationPrompt,
} from "../types";
import { clarificationPromptFromEvent } from "./conversationChat/clarification";
import {
  MINDMAP_SETTINGS_STORAGE_KEY,
  normalizeMindmapMapType,
  type AccessMode,
  type AgentMode,
  type ConversationMindmapSettings,
  type MindmapMapType,
  type SendMessageOptions,
} from "./conversationChat/constants";
import { sendConversationMessage } from "./conversationChat/sendMessage";
import { readStoredJson, readStoredText } from "./storage";

type UseConversationChatParams = {
  projects: SidebarProject[];
  selectedProjectId: string;
  setSelectedProjectId: (projectId: string) => void;
  conversationProjects: Record<string, string>;
  setConversationProjects: Dispatch<SetStateAction<Record<string, string>>>;
  conversationModes: Record<string, AgentMode>;
  setConversationModes: Dispatch<SetStateAction<Record<string, AgentMode>>>;
  defaultIndexId: number | null;
};

type CachedConversationSnapshot = {
  turns: ChatTurn[];
  selectedTurnIndex: number | null;
  infoText: string;
  composerMode: AgentMode;
};

function storageScopeForUser(rawUserId: string | null): string {
  const normalized = String(rawUserId || "default").trim().replace(/[^a-zA-Z0-9._-]/g, "_");
  return normalized || "default";
}

function readStoredMindmapSettings(
  key: string,
  fallbackKey: string,
): Record<string, ConversationMindmapSettings> {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(key) || window.localStorage.getItem(fallbackKey);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Record<string, ConversationMindmapSettings>;
    if (!parsed || typeof parsed !== "object") {
      return {};
    }
    const normalized: Record<string, ConversationMindmapSettings> = {};
    for (const [conversationId, value] of Object.entries(parsed)) {
      if (!value || typeof value !== "object") {
        continue;
      }
      const candidate = value as Partial<ConversationMindmapSettings>;
      normalized[conversationId] = {
        enabled: Boolean(candidate.enabled),
        maxDepth: Math.max(2, Math.min(8, Number(candidate.maxDepth || 4))),
        includeReasoningMap: Boolean(candidate.includeReasoningMap),
        mapType: normalizeMindmapMapType(candidate.mapType),
      };
    }
    return normalized;
  } catch {
    return {};
  }
}

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
  const lastConversationStorageKey = `maia.last-conversation-id:${userStorageScope}`;
  const conversationsCacheStorageKey = `maia.conversations-cache:${userStorageScope}`;
  const conversationDetailCacheStorageKey = `maia.conversation-detail-cache:${userStorageScope}`;
  const cachedConversationId = readStoredText(lastConversationStorageKey, "").trim() || null;
  const cachedConversationSnapshots = readStoredJson<Record<string, CachedConversationSnapshot>>(
    conversationDetailCacheStorageKey,
    {},
  );
  const initialCachedSnapshot = cachedConversationId
    ? cachedConversationSnapshots[cachedConversationId] || null
    : null;

  const [conversations, setConversations] = useState<ConversationSummary[]>(() =>
    readStoredJson<ConversationSummary[]>(conversationsCacheStorageKey, []),
  );
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(cachedConversationId);
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>(() => initialCachedSnapshot?.turns || []);
  const [selectedTurnIndex, setSelectedTurnIndex] = useState<number | null>(() => {
    if (!initialCachedSnapshot?.turns?.length) {
      return null;
    }
    const candidate = Number(initialCachedSnapshot.selectedTurnIndex);
    if (Number.isFinite(candidate) && candidate >= 0 && candidate < initialCachedSnapshot.turns.length) {
      return candidate;
    }
    return initialCachedSnapshot.turns.length - 1;
  });
  const [infoText, setInfoText] = useState(() => initialCachedSnapshot?.infoText || "");
  const [citationMode, setCitationMode] = useState("inline");
  const [mindmapEnabled, setMindmapEnabled] = useState(true);
  const [mindmapMaxDepth, setMindmapMaxDepth] = useState(4);
  const [mindmapIncludeReasoning, setMindmapIncludeReasoning] = useState(true);
  const [mindmapMapType, setMindmapMapType] = useState<MindmapMapType>("structure");
  const [conversationMindmapSettings, setConversationMindmapSettings] = useState<
    Record<string, ConversationMindmapSettings>
  >(() => readStoredMindmapSettings(mindmapSettingsStorageKey, MINDMAP_SETTINGS_STORAGE_KEY));
  const [citationFocus, setCitationFocus] = useState<CitationFocus | null>(null);
  const [composerMode, setComposerMode] = useState<AgentMode>(() => initialCachedSnapshot?.composerMode || "ask");
  const [accessMode, setAccessMode] = useState<AccessMode>("restricted");
  const [activityEvents, setActivityEvents] = useState<AgentActivityEvent[]>([]);
  const [isActivityStreaming, setIsActivityStreaming] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [clarificationPrompt, setClarificationPrompt] = useState<ClarificationPrompt | null>(null);
  const [initialConversationHydrated, setInitialConversationHydrated] = useState(false);
  const selectedConversationIdRef = useRef<string | null>(selectedConversationId);
  const selectedTurnIndexRef = useRef<number | null>(selectedTurnIndex);

  const applyConversationState = useCallback(
    (
      conversationId: string,
      turns: ChatTurn[],
      mode: AgentMode,
      preferredTurnIndex?: number | null,
      fallbackInfoText = "",
    ) => {
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
    },
    [conversationMindmapSettings],
  );

  const stripTurnActivityForCache = useCallback(
    (turns: ChatTurn[]): ChatTurn[] =>
      turns.map((turn) =>
        turn.activityEvents && turn.activityEvents.length > 0
          ? { ...turn, activityEvents: [] }
          : turn,
      ),
    [],
  );

  const refreshConversations = useCallback(async () => {
    const items = await listConversations();
    setConversations(items);
  }, []);

  const visibleConversations = useMemo(
    () =>
      conversations.filter(
        (conversation) =>
          (conversationProjects[conversation.id] || DEFAULT_PROJECT_ID) === selectedProjectId,
      ),
    [conversations, conversationProjects, selectedProjectId],
  );

  const resetConversationDetail = useCallback(() => {
    setChatTurns([]);
    setSelectedTurnIndex(null);
    setInfoText("");
    setActivityEvents([]);
  }, []);

  useEffect(() => {
    if (!selectedConversationId) {
      return;
    }
    const selectedConversationProject = conversationProjects[selectedConversationId] || DEFAULT_PROJECT_ID;
    if (selectedConversationProject !== selectedProjectId) {
      setSelectedConversationId(null);
      resetConversationDetail();
    }
  }, [conversationProjects, resetConversationDetail, selectedConversationId, selectedProjectId]);

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
    stripTurnActivityForCache,
  ]);

  const handleSelectConversation = useCallback(
    async (conversationId: string) => {
      setSelectedConversationId(conversationId);
      const cachedSnapshots = readStoredJson<Record<string, CachedConversationSnapshot>>(
        conversationDetailCacheStorageKey,
        {},
      );
      const cachedSnapshot = cachedSnapshots[conversationId] || null;
      const savedMode = conversationModes[conversationId] || cachedSnapshot?.composerMode || "ask";
      if (cachedSnapshot) {
        applyConversationState(
          conversationId,
          cachedSnapshot.turns || [],
          savedMode,
          cachedSnapshot.selectedTurnIndex,
          cachedSnapshot.infoText,
        );
      }

      const detail = await getConversation(conversationId);
      const { turns, runIds } = buildConversationTurns(detail);
      const baseTurns = turns.map((turn) => ({
        ...turn,
        activityEvents: turn.activityEvents || [],
      }));
      applyConversationState(
        conversationId,
        baseTurns,
        savedMode,
        cachedSnapshot?.selectedTurnIndex,
        cachedSnapshot?.infoText || "",
      );

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
          if (selectedConversationIdRef.current !== conversationId) {
            return;
          }
          const runEventsMap = Object.fromEntries(entries);
          const hydratedTurns = baseTurns.map((turn) =>
            turn.activityRunId
              ? { ...turn, activityEvents: runEventsMap[turn.activityRunId] || [] }
              : turn,
          );
          setChatTurns(hydratedTurns);
          const activeIndex = selectedTurnIndexRef.current;
          if (
            Number.isFinite(activeIndex) &&
            activeIndex !== null &&
            activeIndex >= 0 &&
            activeIndex < hydratedTurns.length
          ) {
            setActivityEvents(hydratedTurns[activeIndex]?.activityEvents || []);
          }
        });
      }
    },
    [applyConversationState, conversationDetailCacheStorageKey, conversationModes],
  );

  const handleCreateConversation = useCallback(
    async (preferredProjectId?: string) => {
      const requestedProjectId = String(preferredProjectId || "").trim();
      const activeProjectId = projects.some((project) => project.id === requestedProjectId)
        ? requestedProjectId
        : projects.some((project) => project.id === selectedProjectId)
          ? selectedProjectId
          : projects[0]?.id || DEFAULT_PROJECT_ID;
      if (activeProjectId !== selectedProjectId) {
        setSelectedProjectId(activeProjectId);
      }

      try {
        const created = await createConversation();
        setConversationProjects((prev) => ({
          ...prev,
          [created.id]: activeProjectId,
        }));
        setConversationModes((prev) => ({
          ...prev,
          [created.id]: composerMode,
        }));
        setSelectedConversationId(created.id);
        resetConversationDetail();
        await refreshConversations();
      } catch (error) {
        setInfoText(`Failed to create a new conversation: ${String(error)}`);
      }
    },
    [
      composerMode,
      projects,
      refreshConversations,
      resetConversationDetail,
      selectedProjectId,
      setConversationModes,
      setConversationProjects,
      setSelectedProjectId,
    ],
  );

  const handleRenameConversation = useCallback(
    async (conversationId: string, name: string) => {
      const normalizedName = name.trim();
      if (!normalizedName) {
        return;
      }
      await updateConversation(conversationId, { name: normalizedName });
      await refreshConversations();
    },
    [refreshConversations],
  );

  const handleDeleteConversation = useCallback(
    async (conversationId: string) => {
      await deleteConversation(conversationId);
      setConversationProjects((prev) => {
        const next = { ...prev };
        delete next[conversationId];
        return next;
      });
      setConversationModes((prev) => {
        const next = { ...prev };
        delete next[conversationId];
        return next;
      });
      if (selectedConversationId === conversationId) {
        setSelectedConversationId(null);
        resetConversationDetail();
      }
      await refreshConversations();
    },
    [
      refreshConversations,
      resetConversationDetail,
      selectedConversationId,
      setConversationModes,
      setConversationProjects,
    ],
  );

  const handleSendMessage = useCallback(
    async (message: string, attachments?: ChatTurn["attachments"], options?: SendMessageOptions) => {
      await sendConversationMessage({
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
    if (!conversations.length || visibleConversations.length > 0) {
      return;
    }
    const fallbackConversation = conversations[0];
    if (!fallbackConversation) {
      return;
    }
    const fallbackProjectId =
      conversationProjects[fallbackConversation.id] || DEFAULT_PROJECT_ID;
    if (fallbackProjectId !== selectedProjectId) {
      setSelectedProjectId(fallbackProjectId);
    }
  }, [
    conversationProjects,
    conversations,
    selectedProjectId,
    setSelectedProjectId,
    visibleConversations.length,
  ]);

  useEffect(() => {
    if (selectedConversationId && !initialConversationHydrated) {
      setInitialConversationHydrated(true);
      void handleSelectConversation(selectedConversationId).catch(() => {
        // Keep the app usable even if hydration selection fails.
      });
      return;
    }
    if (!conversations.length || initialConversationHydrated || selectedConversationId) {
      return;
    }
    if (!visibleConversations.length) {
      return;
    }
    const storedConversationId = readStoredText(lastConversationStorageKey, "").trim();
    const visibleIds = new Set(visibleConversations.map((item) => item.id));
    const candidateConversationId = visibleIds.has(storedConversationId)
      ? storedConversationId
      : visibleConversations[0].id;
    if (!candidateConversationId) {
      setInitialConversationHydrated(true);
      return;
    }
    setInitialConversationHydrated(true);
    void handleSelectConversation(candidateConversationId).catch(() => {
      // Keep the app usable even if hydration selection fails.
    });
  }, [
    conversations.length,
    handleSelectConversation,
    initialConversationHydrated,
    lastConversationStorageKey,
    selectedConversationId,
    visibleConversations,
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
          setChatTurns((prev) => prev.map((turn, index) => (index === turnIndex ? { ...turn, activityEvents: events } : turn)));
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
      const rows = clarificationPrompt.questions.length
        ? clarificationPrompt.questions
        : clarificationPrompt.missingRequirements;
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
        `Continue the paused task from run ${clarificationPrompt.runId || "previous run"}.`,
        `Original request: ${clarificationPrompt.originalRequest}`,
        "Clarification details:",
        ...answeredRows,
        "Proceed with execution now and complete the requested actions.",
      ].join("\n");

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

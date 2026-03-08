import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
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

function readStoredMindmapSettings(): Record<string, ConversationMindmapSettings> {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(MINDMAP_SETTINGS_STORAGE_KEY);
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
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>([]);
  const [selectedTurnIndex, setSelectedTurnIndex] = useState<number | null>(null);
  const [infoText, setInfoText] = useState("");
  const [citationMode, setCitationMode] = useState("inline");
  const [mindmapEnabled, setMindmapEnabled] = useState(true);
  const [mindmapMaxDepth, setMindmapMaxDepth] = useState(4);
  const [mindmapIncludeReasoning, setMindmapIncludeReasoning] = useState(true);
  const [mindmapMapType, setMindmapMapType] = useState<MindmapMapType>("structure");
  const [conversationMindmapSettings, setConversationMindmapSettings] = useState<
    Record<string, ConversationMindmapSettings>
  >(() => readStoredMindmapSettings());
  const [citationFocus, setCitationFocus] = useState<CitationFocus | null>(null);
  const [composerMode, setComposerMode] = useState<AgentMode>("ask");
  const [accessMode, setAccessMode] = useState<AccessMode>("restricted");
  const [activityEvents, setActivityEvents] = useState<AgentActivityEvent[]>([]);
  const [isActivityStreaming, setIsActivityStreaming] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [clarificationPrompt, setClarificationPrompt] = useState<ClarificationPrompt | null>(null);

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
    setComposerMode("ask");
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
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(MINDMAP_SETTINGS_STORAGE_KEY, JSON.stringify(conversationMindmapSettings));
  }, [conversationMindmapSettings]);

  const handleSelectConversation = useCallback(
    async (conversationId: string) => {
      setSelectedConversationId(conversationId);
      const detail = await getConversation(conversationId);
      const { turns, runIds } = buildConversationTurns(detail);

      const runEventsMap: Record<string, AgentActivityEvent[]> = {};
      if (runIds.length > 0) {
        await Promise.all(
          runIds.map(async (runId) => {
            try {
              const rows = await getAgentRunEvents(runId);
              runEventsMap[runId] = extractAgentEvents(rows);
            } catch {
              runEventsMap[runId] = [];
            }
          }),
        );
      }

      const hydratedTurns = turns.map((turn) =>
        turn.activityRunId
          ? { ...turn, activityEvents: runEventsMap[turn.activityRunId] || [] }
          : { ...turn, activityEvents: turn.activityEvents || [] },
      );

      setChatTurns(hydratedTurns);
      setActivityEvents([]);

      const savedMode = conversationModes[conversationId] || "ask";
      setComposerMode(savedMode);
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

      if (hydratedTurns.length > 0) {
        const lastIdx = hydratedTurns.length - 1;
        setSelectedTurnIndex(lastIdx);
        setInfoText(hydratedTurns[lastIdx].info || "");
        setActivityEvents(hydratedTurns[lastIdx].activityEvents || []);
        return;
      }
      setSelectedTurnIndex(null);
      setInfoText("");
    },
    [conversationMindmapSettings, conversationModes],
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

import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import {
  createConversation,
  deleteConversation,
  getAgentRunEvents,
  getConversation,
  listConversations,
  sendChat,
  sendChatStream,
  updateConversation,
  type ConversationSummary,
} from "../../api/client";
import { DEFAULT_PROJECT_ID } from "./constants";
import { buildConversationTurns, extractAgentEvents } from "./eventHelpers";
import type { SidebarProject } from "./types";
import type { AgentActivityEvent, ChatAttachment, ChatTurn, CitationFocus } from "../types";

type AgentMode = "ask" | "company_agent";
type AccessMode = "restricted" | "full_access";

type SendMessageOptions = {
  citationMode?: string;
  useMindmap?: boolean;
  agentMode?: AgentMode;
  accessMode?: AccessMode;
};

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
  const [citationFocus, setCitationFocus] = useState<CitationFocus | null>(null);
  const [composerMode, setComposerMode] = useState<AgentMode>("ask");
  const [accessMode, setAccessMode] = useState<AccessMode>("restricted");
  const [activityEvents, setActivityEvents] = useState<AgentActivityEvent[]>([]);
  const [isActivityStreaming, setIsActivityStreaming] = useState(false);
  const [isSending, setIsSending] = useState(false);

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
    const selectedConversationProject =
      conversationProjects[selectedConversationId] || DEFAULT_PROJECT_ID;
    if (selectedConversationProject !== selectedProjectId) {
      setSelectedConversationId(null);
      resetConversationDetail();
    }
  }, [
    conversationProjects,
    resetConversationDetail,
    selectedConversationId,
    selectedProjectId,
  ]);

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
    [conversationModes],
  );

  const handleCreateConversation = useCallback(async () => {
    const activeProjectId = projects.some((project) => project.id === selectedProjectId)
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
  }, [
    composerMode,
    projects,
    refreshConversations,
    resetConversationDetail,
    selectedProjectId,
    setConversationModes,
    setConversationProjects,
    setSelectedProjectId,
  ]);

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
    async (message: string, attachments?: ChatAttachment[], options?: SendMessageOptions) => {
      if (!message.trim()) {
        return;
      }

      const effectiveMode = options?.agentMode ?? composerMode;
      const effectiveAccessMode = options?.accessMode ?? accessMode;
      const delayedPendingAssistantMessage =
        effectiveMode === "company_agent" ? "Starting my desktop..." : "Thinking....";
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
      const indexSelection =
        attachedFileIds.length > 0 && defaultIndexId !== null
          ? {
              [String(defaultIndexId)]: {
                mode: "select" as const,
                file_ids: attachedFileIds,
              },
            }
          : undefined;

      const pendingTurnIndex = chatTurns.length;
      let delayedPendingTimer: number | null = null;
      const clearDelayedPendingTimer = () => {
        if (delayedPendingTimer !== null) {
          window.clearTimeout(delayedPendingTimer);
          delayedPendingTimer = null;
        }
      };

      setIsSending(true);
      setIsActivityStreaming(effectiveMode === "company_agent");
      setInfoText("");
      setActivityEvents([]);
      setSelectedTurnIndex(pendingTurnIndex);
      setChatTurns((prev) => [
        ...prev,
        {
          user: message,
          assistant: "",
          plot: null,
          attachments: attachments && attachments.length > 0 ? attachments : undefined,
          info: "",
          mode: effectiveMode,
          activityEvents: [],
          needsHumanReview: false,
          humanReviewNotes: null,
          infoPanel: {},
        },
      ]);

      delayedPendingTimer = window.setTimeout(() => {
        setChatTurns((prev) => {
          if (pendingTurnIndex < 0 || pendingTurnIndex >= prev.length) {
            return prev;
          }
          const next = [...prev];
          const turn = next[pendingTurnIndex];
          if (!turn) {
            return prev;
          }
          const hasActivity = Array.isArray(turn.activityEvents) && turn.activityEvents.length > 0;
          const hasAssistantText = Boolean(String(turn.assistant || "").trim());
          if (hasActivity || hasAssistantText) {
            return prev;
          }
          next[pendingTurnIndex] = { ...turn, assistant: delayedPendingAssistantMessage };
          return next;
        });
      }, 5000);

      let streamedEventsLocal: AgentActivityEvent[] = [];
      try {
        const sharedPayload = {
          indexSelection,
          citation: options?.citationMode ?? citationMode,
          useMindmap: options?.useMindmap ?? mindmapEnabled,
          agentMode: effectiveMode,
          accessMode: effectiveAccessMode,
        };

        let response;
        if (effectiveMode === "company_agent") {
          let streamedInfo = "";
          const streamedEvents: AgentActivityEvent[] = [];
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
                  clearDelayedPendingTimer();
                  setChatTurns((prev) => {
                    const next = [...prev];
                    const last = next[next.length - 1];
                    next[next.length - 1] = {
                      ...(last || {}),
                      user: message,
                      assistant: String(event.text || ""),
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
                if (event.type === "activity" && event.event) {
                  clearDelayedPendingTimer();
                  const payload = event.event as AgentActivityEvent;
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
          } catch (streamError) {
            clearDelayedPendingTimer();
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
            console.warn("Company agent stream fallback triggered:", streamError);
          }
        } else {
          response = await sendChat(message, selectedConversationId, sharedPayload);
        }

        clearDelayedPendingTimer();
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
        setInfoText(response.info || "");
        setChatTurns((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          const effectiveReturnedMode =
            (response.mode as AgentMode | undefined) || effectiveMode;
          const backendModeMismatch =
            effectiveMode === "company_agent" && effectiveReturnedMode !== "company_agent";
          next[next.length - 1] = {
            ...(last || {}),
            user: message,
            assistant: backendModeMismatch
              ? `${response.answer || ""}\n\n[Notice] Backend is not running Agent mode. Restart the API server and try again.`
              : response.answer || "",
            info: response.info || "",
            plot: response.plot || null,
            mode: effectiveReturnedMode,
            actionsTaken: response.actions_taken || [],
            sourcesUsed: response.sources_used || [],
            nextRecommendedSteps: response.next_recommended_steps || [],
            needsHumanReview: Boolean(response.needs_human_review),
            humanReviewNotes: response.human_review_notes || null,
            webSummary: response.web_summary || {},
            infoPanel: response.info_panel || {},
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
            previous
              ? `${previous}\n\n[Notice] ${refreshMessage}`
              : `[Notice] ${refreshMessage}`,
          );
        }
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : String(error || "Unknown request failure");
        clearDelayedPendingTimer();
        setChatTurns((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = {
            ...(last || {}),
            user: message,
            assistant: `Error: ${errorMessage}`,
            info: "",
            plot: null,
            mode: effectiveMode,
            needsHumanReview: false,
            humanReviewNotes: null,
            infoPanel: {},
          };
          return next;
        });
      } finally {
        clearDelayedPendingTimer();
        setIsSending(false);
        setIsActivityStreaming(false);
      }
    },
    [
      accessMode,
      chatTurns.length,
      citationMode,
      composerMode,
      defaultIndexId,
      mindmapEnabled,
      refreshConversations,
      selectedConversationId,
      selectedProjectId,
      setConversationModes,
      setConversationProjects,
    ],
  );

  const handleUpdateUserTurn = useCallback((turnIndex: number, message: string) => {
    setChatTurns((prev) =>
      prev.map((turn, idx) => (idx === turnIndex ? { ...turn, user: message } : turn)),
    );
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

  return {
    accessMode,
    activityEvents,
    chatTurns,
    citationFocus,
    citationMode,
    composerMode,
    conversations,
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
    refreshConversations,
    selectedConversationId,
    selectedTurnIndex,
    setAccessMode,
    setCitationFocus,
    setCitationMode,
    setComposerMode,
    setInfoText,
    setMindmapEnabled,
    visibleConversations,
  };
}

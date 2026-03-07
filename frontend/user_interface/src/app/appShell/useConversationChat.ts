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
import type {
  AgentActivityEvent,
  ChatAttachment,
  ChatTurn,
  CitationFocus,
  ClarificationPrompt,
} from "../types";

type AgentMode = "ask" | "company_agent" | "deep_search";
type AccessMode = "restricted" | "full_access";
const MINDMAP_SETTINGS_STORAGE_KEY = "maia.conversation-mindmap-settings";
type MindmapMapType = "structure" | "evidence" | "work_graph";
type ConversationMindmapSettings = {
  enabled: boolean;
  maxDepth: number;
  includeReasoningMap: boolean;
  mapType: MindmapMapType;
};
const DEEP_SEARCH_SETTING_OVERRIDES: Record<string, unknown> = {
  __deep_search_enabled: true,
  __llm_only_keyword_generation: true,
  __llm_only_keyword_generation_strict: true,
  __deep_search_max_source_ids: 350,
  __research_depth_tier: "deep_research",
  __research_web_search_budget: 350,
  __research_max_query_variants: 14,
  __research_results_per_query: 25,
  __research_fused_top_k: 220,
  __research_min_unique_sources: 80,
  __research_source_budget_min: 80,
  __research_source_budget_max: 200,
  __file_research_source_budget_min: 120,
  __file_research_source_budget_max: 220,
  __file_research_max_sources: 220,
  __file_research_max_chunks: 1800,
  __file_research_max_scan_pages: 200,
};

type SendMessageOptions = {
  citationMode?: string;
  useMindmap?: boolean;
  mindmapSettings?: Record<string, unknown>;
  mindmapFocus?: Record<string, unknown>;
  settingOverrides?: Record<string, unknown>;
  agentMode?: AgentMode;
  accessMode?: AccessMode;
};

function normalizeMindmapMapType(raw: unknown): MindmapMapType {
  const value = String(raw || "").trim().toLowerCase();
  if (value === "work_graph") {
    return "work_graph";
  }
  if (value === "evidence") {
    return "evidence";
  }
  return "structure";
}

function readStringList(value: unknown, limit = 8): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const rows = value
    .map((item) => String(item || "").trim())
    .filter((item) => item.length > 0);
  return Array.from(new Set(rows)).slice(0, Math.max(1, limit));
}

function clarificationPromptFromEvent(options: {
  event: AgentActivityEvent;
  originalRequest: string;
  agentMode: AgentMode;
  accessMode: AccessMode;
}): ClarificationPrompt | null {
  const { event, originalRequest, agentMode, accessMode } = options;
  const eventType = String(event.event_type || "").trim().toLowerCase();
  const title = String(event.title || "").trim().toLowerCase();
  const data =
    (event.data && typeof event.data === "object"
      ? (event.data as Record<string, unknown>)
      : event.metadata && typeof event.metadata === "object"
        ? (event.metadata as Record<string, unknown>)
        : {}) || {};
  const missingRequirements = readStringList(data["missing_requirements"], 8);
  const questions = readStringList(data["questions"], 8);
  const likelyClarificationEvent =
    eventType === "llm.clarification_requested" ||
    (eventType === "policy_blocked" && title.includes("clarification")) ||
    (eventType === "policy_blocked" && (missingRequirements.length > 0 || questions.length > 0));
  if (!likelyClarificationEvent) {
    return null;
  }
  const fallbackRows =
    missingRequirements.length > 0
      ? missingRequirements
      : String(event.detail || "")
          .split(";")
          .map((item) => item.trim())
          .filter((item) => item.length > 0)
          .slice(0, 6);
  const normalizedQuestions = questions.length > 0 ? questions : fallbackRows.map((item) => `Please provide: ${item}`);
  if (!normalizedQuestions.length && !fallbackRows.length) {
    return null;
  }
  return {
    runId: String(event.run_id || "").trim(),
    originalRequest: String(originalRequest || "").trim(),
    questions: normalizedQuestions,
    missingRequirements: fallbackRows,
    agentMode,
    accessMode,
  };
}

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
  const [mindmapMaxDepth, setMindmapMaxDepth] = useState(4);
  const [mindmapIncludeReasoning, setMindmapIncludeReasoning] = useState(true);
  const [mindmapMapType, setMindmapMapType] = useState<MindmapMapType>("structure");
  const [conversationMindmapSettings, setConversationMindmapSettings] = useState<
    Record<string, ConversationMindmapSettings>
  >(() => {
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
  });
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

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(
      MINDMAP_SETTINGS_STORAGE_KEY,
      JSON.stringify(conversationMindmapSettings),
    );
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

  const handleCreateConversation = useCallback(async (preferredProjectId?: string) => {
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
      const orchestratorMode = effectiveMode === "company_agent" || effectiveMode === "deep_search";
      const webOnlyResearchRequested =
        effectiveMode === "deep_search" &&
        Boolean(options?.settingOverrides?.["__research_web_only"]);
      const requestedTurnMode: ChatTurn["mode"] =
        effectiveMode === "deep_search" && webOnlyResearchRequested
          ? "web_search"
          : effectiveMode;
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

      const pendingTurnIndex = chatTurns.length;
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
          plot: null,
          attachments: attachments && attachments.length > 0 ? attachments : undefined,
          info: "",
          mode: requestedTurnMode,
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
        const indexSelection =
          Object.keys(selectionByIndex).length > 0
            ? selectionByIndex
            : undefined;

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
                  const payload = event.event as AgentActivityEvent;
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
                    setClarificationPrompt((previous) => {
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
              (options?.mindmapSettings?.["include_reasoning_map"] as boolean) ??
                mindmapIncludeReasoning,
            ),
            mapType:
              normalizeMindmapMapType(options?.mindmapSettings?.["map_type"] || mindmapMapType),
          },
        }));
        setInfoText(response.info || "");
        setChatTurns((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          const effectiveReturnedMode =
            (response.mode as AgentMode | undefined) || effectiveMode;
          const resolvedTurnMode: ChatTurn["mode"] =
            effectiveReturnedMode === "deep_search" && webOnlyResearchRequested
              ? "web_search"
              : effectiveReturnedMode;
          const backendModeMismatch =
            orchestratorMode && effectiveReturnedMode === "ask";
          next[next.length - 1] = {
            ...(last || {}),
            user: message,
            assistant: backendModeMismatch
              ? `${response.answer || ""}\n\n[Notice] Backend is not running orchestrator mode. Restart the API server and try again.`
              : response.answer || "",
            info: response.info || "",
            plot: response.plot || null,
            mode: resolvedTurnMode,
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
            previous
              ? `${previous}\n\n[Notice] ${refreshMessage}`
              : `[Notice] ${refreshMessage}`,
          );
        }
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : String(error || "Unknown request failure");
        setChatTurns((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = {
            ...(last || {}),
            user: message,
            assistant: `Error: ${errorMessage}`,
            info: "",
            plot: null,
            mode: requestedTurnMode,
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
      setConversationMindmapSettings,
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
  }, [
    mindmapEnabled,
    mindmapIncludeReasoning,
    mindmapMapType,
    mindmapMaxDepth,
    selectedConversationId,
  ]);

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
    clarificationPrompt,
    dismissClarificationPrompt: () => setClarificationPrompt(null),
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

import { useCallback, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import {
  createFileGroup,
  deleteFiles,
  deleteFileGroup,
  listFileGroups,
  moveFilesToGroup,
  renameFileGroup,
  createFileIngestionJob,
  createUrlIngestionJob,
  createConversation,
  deleteConversation,
  getAgentRunEvents,
  getConversation,
  listIngestionJobs,
  listConversations,
  listFiles,
  sendChat,
  sendChatStream,
  updateConversation,
  uploadUrls,
  uploadFiles,
  type FileRecord,
  type FileGroupRecord,
  type FileGroupResponse,
  type IngestionJob,
  type ConversationSummary,
  type DeleteFileGroupResponse,
  type MoveFilesToGroupResponse,
  type BulkDeleteFilesResponse,
  type UploadResponse,
} from "../api/client";
import { ChatSidebar } from "./components/ChatSidebar";
import { ChatMain } from "./components/ChatMain";
import { InfoPanel } from "./components/InfoPanel";
import { TopNav } from "./components/TopNav";
import { FilesView } from "./components/FilesView";
import { ResourcesView } from "./components/ResourcesView";
import { SettingsView } from "./components/SettingsView";
import { HelpView } from "./components/HelpView";
import type { AgentActivityEvent, ChatAttachment, ChatTurn, CitationFocus } from "./types";

const LEFT_PANEL_MIN = 240;
const LEFT_PANEL_MAX = 520;
const RIGHT_PANEL_MIN = 280;
const RIGHT_PANEL_MAX = 560;
const CENTER_PANEL_MIN = 460;
const DEFAULT_PROJECT_ID = "project-default";

type SidebarProject = {
  id: string;
  name: string;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function readStoredWidth(key: string, fallback: number) {
  if (typeof window === "undefined") {
    return fallback;
  }
  const value = Number(window.localStorage.getItem(key) || "");
  return Number.isFinite(value) ? value : fallback;
}

function readStoredText(key: string, fallback: string) {
  if (typeof window === "undefined") {
    return fallback;
  }
  const value = window.localStorage.getItem(key);
  return value || fallback;
}

function readStoredJson<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") {
    return fallback;
  }
  const value = window.localStorage.getItem(key);
  if (!value) {
    return fallback;
  }
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

type ResizeSide = "left" | "right" | null;

function ResizeHandle({
  side,
  active,
  onMouseDown,
}: {
  side: "left" | "right";
  active: boolean;
  onMouseDown: (event: ReactMouseEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={side === "left" ? "Resize left panel" : "Resize right panel"}
      onMouseDown={onMouseDown}
      className={`group relative w-2 shrink-0 cursor-col-resize transition-colors ${
        active ? "bg-[#2f2f34]/15" : "hover:bg-[#2f2f34]/10"
      }`}
    >
      <div className="absolute left-1/2 top-1/2 h-12 w-[2px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-black/10 group-hover:bg-[#2f2f34]/60" />
    </div>
  );
}

export default function App() {
  const layoutRef = useRef<HTMLDivElement | null>(null);
  const [activeTab, setActiveTab] = useState("Chat");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isInfoPanelOpen, setIsInfoPanelOpen] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(() =>
    readStoredWidth("maia.sidebar-width", 300),
  );
  const [infoPanelWidth, setInfoPanelWidth] = useState(() =>
    readStoredWidth("maia.info-width", 340),
  );
  const [resizeSide, setResizeSide] = useState<ResizeSide>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [projects, setProjects] = useState<SidebarProject[]>(() => {
    const stored = readStoredJson<SidebarProject[]>("maia.sidebar-projects", []);
    if (stored.length > 0) {
      return stored;
    }
    return [{ id: DEFAULT_PROJECT_ID, name: "General" }];
  });
  const [selectedProjectId, setSelectedProjectId] = useState(() =>
    readStoredText("maia.selected-project", DEFAULT_PROJECT_ID),
  );
  const [conversationProjects, setConversationProjects] = useState<Record<string, string>>(() =>
    readStoredJson<Record<string, string>>("maia.conversation-projects", {}),
  );
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(
    null,
  );
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>([]);
  const [selectedTurnIndex, setSelectedTurnIndex] = useState<number | null>(null);
  const [infoText, setInfoText] = useState("");
  const [uploadStatus, setUploadStatus] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [fileCount, setFileCount] = useState(0);
  const [indexedFiles, setIndexedFiles] = useState<FileRecord[]>([]);
  const [fileGroups, setFileGroups] = useState<FileGroupRecord[]>([]);
  const [defaultIndexId, setDefaultIndexId] = useState<number | null>(null);
  const [ingestionJobs, setIngestionJobs] = useState<IngestionJob[]>([]);
  const [citationMode, setCitationMode] = useState("inline");
  const [mindmapEnabled, setMindmapEnabled] = useState(true);
  const [citationFocus, setCitationFocus] = useState<CitationFocus | null>(null);
  const [conversationModes, setConversationModes] = useState<Record<string, "ask" | "company_agent">>(() =>
    readStoredJson<Record<string, "ask" | "company_agent">>("maia.conversation-modes", {}),
  );
  const [composerMode, setComposerMode] = useState<"ask" | "company_agent">("ask");
  const [accessMode, setAccessMode] = useState<"restricted" | "full_access">("restricted");
  const [activityEvents, setActivityEvents] = useState<AgentActivityEvent[]>([]);
  const [isActivityStreaming, setIsActivityStreaming] = useState(false);

  const refreshConversations = useCallback(async () => {
    const items = await listConversations();
    setConversations(items);
  }, []);

  const refreshFileCount = useCallback(async () => {
    const filesPayload = await listFiles();
    setFileCount(filesPayload.files.length);
    setIndexedFiles(filesPayload.files);
    setDefaultIndexId(filesPayload.index_id);
    try {
      const groupsPayload = await listFileGroups({ indexId: filesPayload.index_id });
      setFileGroups(groupsPayload.groups);
    } catch {
      setFileGroups([]);
    }
  }, []);

  const refreshIngestionJobs = useCallback(async () => {
    const jobs = await listIngestionJobs(80);
    setIngestionJobs(jobs);
  }, []);

  const visibleConversations = conversations.filter(
    (conversation) =>
      (conversationProjects[conversation.id] || DEFAULT_PROJECT_ID) === selectedProjectId,
  );

  useEffect(() => {
    const load = async () => {
      try {
        await Promise.all([refreshConversations(), refreshFileCount(), refreshIngestionJobs()]);
      } catch {
        // Keep UI available even if backend is not ready.
      }
    };
    void load();
  }, [refreshConversations, refreshFileCount, refreshIngestionJobs]);

  useEffect(() => {
    const hasActiveJobs = ingestionJobs.some(
      (job) => job.status === "queued" || job.status === "running",
    );
    if (!hasActiveJobs) {
      return;
    }
    const timer = window.setInterval(() => {
      void Promise.all([refreshIngestionJobs(), refreshFileCount()]);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [ingestionJobs, refreshIngestionJobs, refreshFileCount]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem("maia.sidebar-width", String(Math.round(sidebarWidth)));
  }, [sidebarWidth]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem("maia.info-width", String(Math.round(infoPanelWidth)));
  }, [infoPanelWidth]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem("maia.sidebar-projects", JSON.stringify(projects));
  }, [projects]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem("maia.selected-project", selectedProjectId);
  }, [selectedProjectId]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(
      "maia.conversation-projects",
      JSON.stringify(conversationProjects),
    );
  }, [conversationProjects]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem("maia.conversation-modes", JSON.stringify(conversationModes));
  }, [conversationModes]);

  useEffect(() => {
    if (!projects.some((project) => project.id === selectedProjectId)) {
      setSelectedProjectId(projects[0]?.id || DEFAULT_PROJECT_ID);
    }
  }, [projects, selectedProjectId]);

  useEffect(() => {
    if (!selectedConversationId) {
      return;
    }
    const selectedConversationProject =
      conversationProjects[selectedConversationId] || DEFAULT_PROJECT_ID;
    if (selectedConversationProject !== selectedProjectId) {
      setSelectedConversationId(null);
      setChatTurns([]);
      setSelectedTurnIndex(null);
      setInfoText("");
      setActivityEvents([]);
      setComposerMode("ask");
    }
  }, [conversationProjects, selectedConversationId, selectedProjectId]);

  useEffect(() => {
    const layout = layoutRef.current;
    if (!layout) {
      return;
    }
    const bounds = layout.getBoundingClientRect();
    const availableWidth = bounds.width;
    const leftMax = Math.max(
      LEFT_PANEL_MIN,
      availableWidth - CENTER_PANEL_MIN - (isInfoPanelOpen ? infoPanelWidth : 0),
    );
    const rightMax = Math.max(
      RIGHT_PANEL_MIN,
      availableWidth - CENTER_PANEL_MIN - (isSidebarCollapsed ? 64 : sidebarWidth),
    );
    const nextLeft = clamp(sidebarWidth, LEFT_PANEL_MIN, Math.min(LEFT_PANEL_MAX, leftMax));
    const nextRight = clamp(infoPanelWidth, RIGHT_PANEL_MIN, Math.min(RIGHT_PANEL_MAX, rightMax));
    if (nextLeft !== sidebarWidth) {
      setSidebarWidth(nextLeft);
    }
    if (nextRight !== infoPanelWidth) {
      setInfoPanelWidth(nextRight);
    }
  }, [isInfoPanelOpen, isSidebarCollapsed, sidebarWidth, infoPanelWidth]);

  useEffect(() => {
    if (!resizeSide) {
      return;
    }

    const onMove = (event: MouseEvent) => {
      const layout = layoutRef.current;
      if (!layout) {
        return;
      }
      const bounds = layout.getBoundingClientRect();
      const availableWidth = bounds.width;
      if (resizeSide === "left" && !isSidebarCollapsed) {
        const maxLeft = Math.max(
          LEFT_PANEL_MIN,
          availableWidth - CENTER_PANEL_MIN - (isInfoPanelOpen ? infoPanelWidth : 0),
        );
        const proposed = event.clientX - bounds.left;
        setSidebarWidth(clamp(proposed, LEFT_PANEL_MIN, Math.min(LEFT_PANEL_MAX, maxLeft)));
      }
      if (resizeSide === "right" && isInfoPanelOpen) {
        const maxRight = Math.max(
          RIGHT_PANEL_MIN,
          availableWidth - CENTER_PANEL_MIN - (isSidebarCollapsed ? 64 : sidebarWidth),
        );
        const proposed = bounds.right - event.clientX;
        setInfoPanelWidth(clamp(proposed, RIGHT_PANEL_MIN, Math.min(RIGHT_PANEL_MAX, maxRight)));
      }
    };

    const onStop = () => setResizeSide(null);
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onStop);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onStop);
    };
  }, [resizeSide, isInfoPanelOpen, isSidebarCollapsed, infoPanelWidth, sidebarWidth]);

  const handleSelectConversation = async (conversationId: string) => {
    setSelectedConversationId(conversationId);
    const detail = await getConversation(conversationId);
    const messages = detail.data_source?.messages || [];
    const retrievalMessages = detail.data_source?.retrieval_messages || [];
    const messageMeta = (detail.data_source?.message_meta || []) as Array<{
      mode?: "ask" | "company_agent";
      actions_taken?: ChatTurn["actionsTaken"];
      sources_used?: ChatTurn["sourcesUsed"];
      next_recommended_steps?: string[];
      activity_run_id?: string | null;
    }>;
    const turns = messages.map((entry, index) => ({
      user: entry[0] || "",
      assistant: entry[1] || "",
      info: retrievalMessages[index] || "",
      mode: messageMeta[index]?.mode || "ask",
      actionsTaken: messageMeta[index]?.actions_taken || [],
      sourcesUsed: messageMeta[index]?.sources_used || [],
      nextRecommendedSteps: messageMeta[index]?.next_recommended_steps || [],
      activityRunId: messageMeta[index]?.activity_run_id || null,
    }));
    const runIds = Array.from(
      new Set(
        turns
          .map((turn) => turn.activityRunId)
          .filter((value): value is string => Boolean(value)),
      ),
    );
    const runEventsMap: Record<string, AgentActivityEvent[]> = {};
    if (runIds.length > 0) {
      await Promise.all(
        runIds.map(async (runId) => {
          try {
            const rows = await getAgentRunEvents(runId);
            runEventsMap[runId] = rows
              .filter((row) => row.type === "event")
              .map((row) => row.payload)
              .filter((payload): payload is AgentActivityEvent =>
                Boolean(payload && typeof payload === "object" && "event_id" in (payload as object)),
              );
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
  };

  const handleCreateConversation = async () => {
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
      setChatTurns([]);
      setSelectedTurnIndex(null);
      setInfoText("");
      setActivityEvents([]);
      await refreshConversations();
    } catch (error) {
      setInfoText(`Failed to create a new conversation: ${String(error)}`);
    }
  };

  const handleCreateProject = (name: string) => {
    const normalizedName = name.trim();
    if (!normalizedName) {
      return;
    }

    const existing = projects.find(
      (project) => project.name.toLowerCase() === normalizedName.toLowerCase(),
    );
    if (existing) {
      setSelectedProjectId(existing.id);
      return;
    }

    const newProjectId = `project-${Date.now().toString(36)}-${Math.random()
      .toString(36)
      .slice(2, 6)}`;
    const nextProject: SidebarProject = {
      id: newProjectId,
      name: normalizedName,
    };
    setProjects((prev) => [...prev, nextProject]);
    setSelectedProjectId(newProjectId);
  };

  const handleRenameProject = (projectId: string, name: string) => {
    const normalizedName = name.trim();
    if (!normalizedName) {
      return;
    }
    const duplicate = projects.find(
      (project) =>
        project.id !== projectId && project.name.toLowerCase() === normalizedName.toLowerCase(),
    );
    if (duplicate) {
      return;
    }
    setProjects((prev) =>
      prev.map((project) =>
        project.id === projectId ? { ...project, name: normalizedName } : project,
      ),
    );
  };

  const handleDeleteProject = (projectId: string) => {
    if (projects.length <= 1) {
      return;
    }

    const remainingProjects = projects.filter((project) => project.id !== projectId);
    if (!remainingProjects.length) {
      return;
    }

    const fallbackProjectId =
      remainingProjects.find((project) => project.id === DEFAULT_PROJECT_ID)?.id ||
      remainingProjects[0].id;

    setProjects(remainingProjects);
    setConversationProjects((prev) => {
      const next = { ...prev };
      Object.entries(next).forEach(([conversationId, assignedProjectId]) => {
        if (assignedProjectId === projectId) {
          next[conversationId] = fallbackProjectId;
        }
      });
      return next;
    });

    if (selectedProjectId === projectId) {
      setSelectedProjectId(fallbackProjectId);
    }
  };

  const handleMoveConversationToProject = (conversationId: string, projectId: string) => {
    setConversationProjects((prev) => ({
      ...prev,
      [conversationId]: projectId,
    }));
  };

  const handleRenameConversation = async (conversationId: string, name: string) => {
    const normalizedName = name.trim();
    if (!normalizedName) {
      return;
    }
    await updateConversation(conversationId, { name: normalizedName });
    await refreshConversations();
  };

  const handleDeleteConversation = async (conversationId: string) => {
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
      setChatTurns([]);
      setSelectedTurnIndex(null);
      setInfoText("");
      setActivityEvents([]);
    }
    await refreshConversations();
  };

  const handleSendMessage = async (
    message: string,
    attachments?: ChatAttachment[],
    options?: {
      citationMode?: string;
      useMindmap?: boolean;
      agentMode?: "ask" | "company_agent";
      accessMode?: "restricted" | "full_access";
    },
  ) => {
    if (!message.trim()) {
      return;
    }

    const effectiveMode = options?.agentMode ?? composerMode;
    const effectiveAccessMode = options?.accessMode ?? accessMode;
    const pendingAssistantMessage =
      effectiveMode === "company_agent" ? "Starting my desktop..." : "Thinking....";

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
    setIsSending(true);
    setIsActivityStreaming(effectiveMode === "company_agent");
    setInfoText("");
    setActivityEvents([]);
    setSelectedTurnIndex(pendingTurnIndex);
    setChatTurns((prev) => [
      ...prev,
      {
        user: message,
        assistant: pendingAssistantMessage,
        attachments: attachments && attachments.length > 0 ? attachments : undefined,
        info: "",
        mode: effectiveMode,
        activityEvents: [],
      },
    ]);

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
              if (event.type === "activity" && event.event) {
                const payload = event.event as AgentActivityEvent;
                streamedEvents.push(payload);
                streamedEventsLocal = [...streamedEvents];
                setActivityEvents([...streamedEvents]);
                setChatTurns((prev) => {
                  const next = [...prev];
                  const last = next[next.length - 1];
                  next[next.length - 1] = {
                    ...(last || {}),
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
          console.warn("Company agent stream fallback triggered:", streamError);
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
      setInfoText(response.info || "");
      setChatTurns((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        const effectiveReturnedMode =
          (response.mode as "ask" | "company_agent" | undefined) || effectiveMode;
        const backendModeMismatch =
          effectiveMode === "company_agent" && effectiveReturnedMode !== "company_agent";
        next[next.length - 1] = {
          ...(last || {}),
          user: message,
          assistant: backendModeMismatch
            ? `${response.answer || ""}\n\n[Notice] Backend is not running Company Agent mode. Restart the API server and try again.`
            : response.answer || "",
          info: response.info || "",
          mode: effectiveReturnedMode,
          actionsTaken: response.actions_taken || [],
          sourcesUsed: response.sources_used || [],
          nextRecommendedSteps: response.next_recommended_steps || [],
          activityRunId: response.activity_run_id || null,
          activityEvents: streamedEventsLocal,
        };
        return next;
      });
      setActivityEvents(streamedEventsLocal);
      setSelectedTurnIndex(pendingTurnIndex);
      await refreshConversations();
    } catch (error) {
      setChatTurns((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = {
          ...(last || {}),
          user: message,
          assistant: `Error: ${String(error)}`,
          info: "",
          mode: effectiveMode,
        };
        return next;
      });
    } finally {
      setIsSending(false);
      setIsActivityStreaming(false);
    }
  };

  const handleUpdateUserTurn = (turnIndex: number, message: string) => {
    setChatTurns((prev) =>
      prev.map((turn, idx) => (idx === turnIndex ? { ...turn, user: message } : turn)),
    );
  };

  const handleUploadFiles = async (
    files: FileList,
    options?: {
      scope?: "persistent" | "chat_temp";
      showStatus?: boolean;
    },
  ): Promise<UploadResponse> => {
    if (!files.length) {
      throw new Error("No files selected.");
    }

    const scope = options?.scope ?? "persistent";
    const showStatus = options?.showStatus ?? scope !== "chat_temp";
    if (showStatus) {
      setUploadStatus("Uploading files...");
    }
    try {
      const response = await uploadFiles(files, { scope });
      const successCount = response.items.filter((item) => item.status === "success").length;
      if (showStatus) {
        if (response.errors.length > 0) {
          setUploadStatus(`Upload issue: ${response.errors[0]}`);
        } else {
          setUploadStatus(`Indexed ${successCount} file(s).`);
        }
      }
      if (scope !== "chat_temp") {
        await refreshFileCount();
      }
      return response;
    } catch (error) {
      if (showStatus) {
        setUploadStatus(`Upload failed: ${String(error)}`);
      }
      throw error;
    }
  };

  const handleUploadFilesForChat = async (files: FileList): Promise<UploadResponse> => {
    return handleUploadFiles(files, {
      scope: "chat_temp",
      showStatus: false,
    });
  };

  const handleUploadUrlsToLibrary = async (
    urlText: string,
    options?: {
      reindex?: boolean;
      web_crawl_depth?: number;
      web_crawl_max_pages?: number;
      web_crawl_same_domain_only?: boolean;
      include_pdfs?: boolean;
      include_images?: boolean;
    },
  ): Promise<UploadResponse> => {
    if (!urlText.trim()) {
      throw new Error("No URLs were provided.");
    }

    setUploadStatus("Indexing URLs...");
    try {
      const response = await uploadUrls(urlText, {
        reindex: options?.reindex ?? false,
        web_crawl_depth: options?.web_crawl_depth ?? 0,
        web_crawl_max_pages: options?.web_crawl_max_pages ?? 0,
        web_crawl_same_domain_only: options?.web_crawl_same_domain_only ?? true,
        include_pdfs: options?.include_pdfs ?? true,
        include_images: options?.include_images ?? true,
      });
      const successCount = response.items.filter((item) => item.status === "success").length;
      if (response.errors.length > 0) {
        setUploadStatus(`URL indexing issue: ${response.errors[0]}`);
      } else {
        setUploadStatus(`Indexed ${successCount} URL source(s).`);
      }
      await refreshFileCount();
      return response;
    } catch (error) {
      setUploadStatus(`URL indexing failed: ${String(error)}`);
      throw error;
    }
  };

  const isMissingJobEndpointError = (error: unknown) => {
    const text = String(error || "");
    return (
      text.includes("Method Not Allowed") ||
      text.includes("Not Found") ||
      text.includes("404") ||
      text.includes("405")
    );
  };

  const handleCreateFileIngestionJob = async (
    files: FileList,
    options?: { reindex?: boolean },
  ) => {
    if (!files.length) {
      throw new Error("No files selected.");
    }

    setUploadStatus("Queueing ingestion job...");
    try {
      const job = await createFileIngestionJob(files, {
        reindex: options?.reindex ?? false,
        indexId: defaultIndexId ?? undefined,
      });
      setUploadStatus(
        `Job queued: ${job.id.slice(0, 8)} (${job.total_items} item${job.total_items === 1 ? "" : "s"}).`,
      );
      await refreshIngestionJobs();
      return job;
    } catch (error) {
      if (isMissingJobEndpointError(error)) {
        setUploadStatus(
          "Async ingestion endpoint unavailable on this server. Uploading with sync fallback...",
        );
        const response = await handleUploadFiles(files);
        await refreshIngestionJobs();
        return {
          id: `fallback-sync-${Date.now()}`,
          user_id: "default",
          kind: "files",
          status: "completed",
          index_id: defaultIndexId,
          reindex: options?.reindex ?? false,
          total_items: files.length,
          processed_items: files.length,
          success_count: response.items.filter((item) => item.status === "success").length,
          failure_count: response.items.filter((item) => item.status !== "success").length,
          items: response.items,
          errors: response.errors,
          file_ids: response.file_ids,
          debug: response.debug,
          message: "Completed via sync upload fallback.",
          date_created: new Date().toISOString(),
          date_updated: new Date().toISOString(),
          date_started: new Date().toISOString(),
          date_finished: new Date().toISOString(),
        };
      }
      setUploadStatus(`Failed to queue file ingestion job: ${String(error)}`);
      throw error;
    }
  };

  const handleCreateUrlIngestionJob = async (
    urlText: string,
    options?: { reindex?: boolean },
  ) => {
    if (!urlText.trim()) {
      throw new Error("No URLs were provided.");
    }

    setUploadStatus("Queueing URL ingestion job...");
    try {
      const job = await createUrlIngestionJob(urlText, {
        reindex: options?.reindex ?? false,
        indexId: defaultIndexId ?? undefined,
        web_crawl_depth: 0,
        web_crawl_max_pages: 0,
        web_crawl_same_domain_only: true,
        include_pdfs: true,
        include_images: true,
      });
      setUploadStatus(
        `URL job queued: ${job.id.slice(0, 8)} (${job.total_items} item${job.total_items === 1 ? "" : "s"}).`,
      );
      await refreshIngestionJobs();
      return job;
    } catch (error) {
      if (isMissingJobEndpointError(error)) {
        setUploadStatus(
          "Async URL endpoint unavailable on this server. Indexing URLs with sync fallback...",
        );
        const response = await uploadUrls(urlText, {
          reindex: options?.reindex ?? false,
          web_crawl_depth: 0,
          web_crawl_max_pages: 0,
          web_crawl_same_domain_only: true,
          include_pdfs: true,
          include_images: true,
        });
        await refreshFileCount();
        await refreshIngestionJobs();
        const total = urlText
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean).length;
        return {
          id: `fallback-sync-${Date.now()}`,
          user_id: "default",
          kind: "urls",
          status: "completed",
          index_id: defaultIndexId,
          reindex: options?.reindex ?? false,
          total_items: total,
          processed_items: total,
          success_count: response.items.filter((item) => item.status === "success").length,
          failure_count: response.items.filter((item) => item.status !== "success").length,
          items: response.items,
          errors: response.errors,
          file_ids: response.file_ids,
          debug: response.debug,
          message: "Completed via sync URL fallback.",
          date_created: new Date().toISOString(),
          date_updated: new Date().toISOString(),
          date_started: new Date().toISOString(),
          date_finished: new Date().toISOString(),
        };
      }
      setUploadStatus(`Failed to queue URL ingestion job: ${String(error)}`);
      throw error;
    }
  };

  const handleDeleteFiles = async (fileIds: string[]): Promise<BulkDeleteFilesResponse> => {
    if (!fileIds.length) {
      throw new Error("No files selected.");
    }

    const uniqueIds = Array.from(new Set(fileIds.filter(Boolean)));
    const chunkSize = 100;
    const deletedIds: string[] = [];
    const failed: BulkDeleteFilesResponse["failed"] = [];
    let resolvedIndexId = defaultIndexId ?? 0;

    for (let offset = 0; offset < uniqueIds.length; offset += chunkSize) {
      const chunk = uniqueIds.slice(offset, offset + chunkSize);
      try {
        const response = await deleteFiles(chunk, {
          indexId: defaultIndexId ?? undefined,
        });
        resolvedIndexId = response.index_id;
        deletedIds.push(...response.deleted_ids);
        failed.push(...response.failed);
      } catch (error) {
        const message = String(error);
        failed.push(
          ...chunk.map((fileId) => ({
            file_id: fileId,
            status: "failed",
            message,
          })),
        );
      }
    }

    await refreshFileCount();
    return {
      index_id: resolvedIndexId,
      deleted_ids: deletedIds,
      failed,
    };
  };

  const handleMoveFilesToGroup = async (
    fileIds: string[],
    options?: {
      groupId?: string;
      groupName?: string;
      mode?: "append" | "replace";
    },
  ): Promise<MoveFilesToGroupResponse> => {
    if (!fileIds.length) {
      throw new Error("No files selected.");
    }
    const response = await moveFilesToGroup(fileIds, {
      groupId: options?.groupId,
      groupName: options?.groupName,
      mode: options?.mode ?? "append",
      indexId: defaultIndexId ?? undefined,
    });
    await refreshFileCount();
    return response;
  };

  const handleCreateFileGroup = async (
    name: string,
    fileIds?: string[],
  ): Promise<MoveFilesToGroupResponse> => {
    const response = await createFileGroup(name, fileIds || [], {
      indexId: defaultIndexId ?? undefined,
    });
    await refreshFileCount();
    return response;
  };

  const handleRenameFileGroup = async (
    groupId: string,
    name: string,
  ): Promise<FileGroupResponse> => {
    const response = await renameFileGroup(groupId, name, {
      indexId: defaultIndexId ?? undefined,
    });
    await refreshFileCount();
    return response;
  };

  const handleDeleteFileGroup = async (
    groupId: string,
  ): Promise<DeleteFileGroupResponse> => {
    const response = await deleteFileGroup(groupId, {
      indexId: defaultIndexId ?? undefined,
    });
    await refreshFileCount();
    return response;
  };

  return (
    <div className="size-full flex flex-col bg-[#f5f5f7] overflow-hidden">
      <TopNav activeTab={activeTab} onTabChange={setActiveTab} />
      <div ref={layoutRef} className="flex-1 min-h-0 flex overflow-hidden">
        {activeTab === "Chat" ? (
          <>
            <ChatSidebar
              isCollapsed={isSidebarCollapsed}
              width={sidebarWidth}
              onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
              conversations={visibleConversations}
              allConversations={conversations}
              selectedConversationId={
                selectedConversationId &&
                visibleConversations.some((conversation) => conversation.id === selectedConversationId)
                  ? selectedConversationId
                  : null
              }
              onSelectConversation={handleSelectConversation}
              onNewConversation={handleCreateConversation}
              projects={projects}
              selectedProjectId={selectedProjectId}
              onSelectProject={setSelectedProjectId}
              onCreateProject={handleCreateProject}
              onRenameProject={handleRenameProject}
              onDeleteProject={handleDeleteProject}
              canDeleteProject={projects.length > 1}
              conversationProjects={conversationProjects}
              onMoveConversationToProject={handleMoveConversationToProject}
              onRenameConversation={handleRenameConversation}
              onDeleteConversation={handleDeleteConversation}
              onOpenWorkspaceTab={(tab) => setActiveTab(tab)}
            />

            {!isSidebarCollapsed ? (
              <ResizeHandle
                side="left"
                active={resizeSide === "left"}
                onMouseDown={(event) => {
                  event.preventDefault();
                  setResizeSide("left");
                }}
              />
            ) : null}

            <ChatMain
              onToggleInfoPanel={() => setIsInfoPanelOpen(!isInfoPanelOpen)}
              isInfoPanelOpen={isInfoPanelOpen}
              chatTurns={chatTurns}
              selectedTurnIndex={selectedTurnIndex}
              onSelectTurn={(turnIndex) => {
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
                      const events = rows
                        .filter((row) => row.type === "event")
                        .map((row) => row.payload)
                        .filter((payload): payload is AgentActivityEvent =>
                          Boolean(payload && typeof payload === "object" && "event_id" in (payload as object)),
                        );
                      setActivityEvents(events);
                      setChatTurns((prev) =>
                        prev.map((turn, index) =>
                          index === turnIndex ? { ...turn, activityEvents: events } : turn,
                        ),
                      );
                    })
                    .catch(() => setActivityEvents([]));
                  return;
                }
                setActivityEvents([]);
              }}
              onUpdateUserTurn={handleUpdateUserTurn}
              onSendMessage={handleSendMessage}
              onUploadFiles={handleUploadFilesForChat}
              isSending={isSending}
              citationMode={citationMode}
              onCitationModeChange={setCitationMode}
              mindmapEnabled={mindmapEnabled}
              onMindmapEnabledChange={setMindmapEnabled}
              agentMode={composerMode}
              onAgentModeChange={(mode) => {
                setComposerMode(mode);
                if (selectedConversationId) {
                  setConversationModes((prev) => ({
                    ...prev,
                    [selectedConversationId]: mode,
                  }));
                }
              }}
              accessMode={accessMode}
              onAccessModeChange={setAccessMode}
              activityEvents={activityEvents}
              isActivityStreaming={isActivityStreaming}
              onCitationClick={(citation) => {
                setCitationFocus(citation);
                setActiveTab("Chat");
                setIsInfoPanelOpen(true);
              }}
            />

            {isInfoPanelOpen ? (
              <ResizeHandle
                side="right"
                active={resizeSide === "right"}
                onMouseDown={(event) => {
                  event.preventDefault();
                  setResizeSide("right");
                }}
              />
            ) : null}

            {isInfoPanelOpen ? (
              <InfoPanel
                width={infoPanelWidth}
                messageCount={chatTurns.length}
                sourceCount={fileCount}
                infoText={infoText}
                answerText={
                  selectedTurnIndex !== null ? chatTurns[selectedTurnIndex]?.assistant || "" : ""
                }
                questionText={
                  selectedTurnIndex !== null ? chatTurns[selectedTurnIndex]?.user || "" : ""
                }
                citationFocus={citationFocus}
                indexId={defaultIndexId}
                onClearCitationFocus={() => setCitationFocus(null)}
              />
            ) : null}
          </>
        ) : activeTab === "Files" ? (
          <FilesView
            citationFocus={null}
            indexId={defaultIndexId}
            files={indexedFiles}
            fileGroups={fileGroups}
            onRefreshFiles={refreshFileCount}
            onUploadFiles={handleUploadFiles}
            onUploadUrls={handleUploadUrlsToLibrary}
            onDeleteFiles={handleDeleteFiles}
            onMoveFilesToGroup={handleMoveFilesToGroup}
            onCreateFileGroup={handleCreateFileGroup}
            onRenameFileGroup={handleRenameFileGroup}
            onDeleteFileGroup={handleDeleteFileGroup}
            ingestionJobs={ingestionJobs}
            onRefreshIngestionJobs={refreshIngestionJobs}
            uploadStatus={uploadStatus}
          />
        ) : activeTab === "Resources" ? (
          <ResourcesView />
        ) : activeTab === "Settings" ? (
          <SettingsView />
        ) : activeTab === "Help" ? (
          <HelpView />
        ) : (
          <div className="flex-1 flex items-center justify-center bg-white">
            <p className="text-[15px] text-[#86868b]">{activeTab} content coming soon...</p>
          </div>
        )}
      </div>
    </div>
  );
}
